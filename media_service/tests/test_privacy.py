import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_session
from app.inference import PredictionOutput
from app.models import Annotation, AnnotationTask, Frame, ProcessingJob, SanitizedExport, Video
from app.privacy import (
    BlurSegment,
    build_ffmpeg_blur_filter,
    build_ffmpeg_mask_filter,
    build_mask_segments,
)
from app.service import (
    claim_next_job,
    process_sanitization_job,
    record_sanitization_failure,
    rectangle_union_area,
)
from app.storage import LocalStorage


class FakeSanitizationProcessor:
    def __init__(self):
        self.command = None

    def _run(self, command, _):
        self.command = command
        Path(command[-1]).write_bytes(b"sanitized-video")

    def extract_frames(self, _, output_dir, sample_fps):
        assert sample_fps > 0
        output_dir.mkdir(parents=True, exist_ok=True)
        frame = output_dir / "frame-000001.jpg"
        frame.write_bytes(b"frame")
        return [frame]


class FakeResidualProvider:
    runtime_version = "residual-test-v1"

    def __init__(self, findings=None):
        self.findings = findings or []

    def infer_frames(self, image_paths, model_kind, confidence_threshold, device):
        assert model_kind == "pii"
        return [self.findings for _ in image_paths]

    def infer_frame(self, image_path, model_kind, confidence_threshold, device):
        assert model_kind == "pii"
        assert image_path.exists()
        return self.findings


class BrokenResidualProvider(FakeResidualProvider):
    def infer_frame(self, image_path, model_kind, confidence_threshold, device):
        raise RuntimeError("residual model unavailable")

    def infer_frames(self, image_paths, model_kind, confidence_threshold, device):
        raise RuntimeError("residual model unavailable")


def make_database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_ffmpeg_filter_chains_local_blur_regions():
    filter_graph, output = build_ffmpeg_blur_filter(
        [
            BlurSegment("a", "face", 0, 0.5, 10, 20, 100, 120),
            BlurSegment("b", "screen", 0.5, 1, 200, 100, 80, 60),
        ]
    )

    assert "crop=100:120:10:20,boxblur=10:2" in filter_graph
    assert "between(t,0.500,1.000)" in filter_graph
    assert output == "[privacy1]"


def test_rectangle_union_area_does_not_double_count_overlaps():
    assert rectangle_union_area([(0, 0, 10, 10), (5, 5, 15, 15)]) == 175


def test_pixel_mask_filter_renders_only_enabled_cells():
    video = Video(width=80, height=40, duration_ms=1000, sample_fps=1)
    frame = Frame(id="frame-1", frame_number=1, timestamp_ms=0)
    video.frames = [frame]
    annotation = Annotation(
        id="mask-1",
        frame_id=frame.id,
        label="face",
        annotation_type="mask",
        geometry={
            "encoding": "row-major-rle-v1",
            "width": 8,
            "height": 8,
            "rle": [18, 4, 4, 4, 4, 4, 26],
            "bbox": {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.375},
        },
    )

    segments = build_mask_segments(video, [annotation])
    filter_graph, output = build_ffmpeg_mask_filter(80, 40, segments)

    assert segments[0].covered_cells == 12
    assert "drawbox=" in filter_graph
    assert "maskedmerge" in filter_graph
    assert output == "[privacymasked]"


def test_privacy_export_api_and_worker_create_audited_artifacts(tmp_path):
    Session = make_database()
    storage = LocalStorage(tmp_path)
    with Session() as session:
        video = Video(
            filename="ride.mp4",
            storage_path="videos/ride.mp4",
            file_size=10,
            status="READY_FOR_ANNOTATION",
            duration_ms=2000,
            width=640,
            height=360,
            sample_fps=1,
        )
        frames = [
            Frame(
                video=video,
                frame_number=index,
                timestamp_ms=(index - 1) * 1000,
                storage_path=f"frames/privacy/{index}.jpg",
            )
            for index in (1, 2)
        ]
        task = AnnotationTask(video=video, status="COMPLETED")
        annotation = Annotation(
            task=task,
            frame=frames[0],
            label="face",
            annotation_type="bbox",
            geometry={"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.3},
        )
        session.add_all([video, *frames, task, annotation])
        session.commit()
        video_id, task_id = video.id, task.id
        source = storage.absolute_path(video.storage_path)
        source.parent.mkdir(parents=True)
        source.write_bytes(b"source-video")

    def test_session():
        with Session() as session:
            yield session

    main.app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(main.app) as client:
            created = client.post(
                f"/api/videos/{video_id}/sanitized-exports",
                json={"task_id": task_id, "reviewer": "reviewer-a"},
            )
    finally:
        main.app.dependency_overrides.clear()

    assert created.status_code == 202
    assert created.json()["sanitized_export"]["source_annotation_count"] == 1
    processor = FakeSanitizationProcessor()
    with Session() as session:
        job_id = claim_next_job(session)
        process_sanitization_job(
            session,
            job_id,
            processor=processor,
            storage=storage,
            residual_provider=FakeResidualProvider(),
        )
        item = session.scalar(select(SanitizedExport))
        manifest = json.loads(storage.absolute_path(item.manifest_path).read_text())

        assert item.status == "COMPLETED"
        assert item.output_sha256
        assert manifest["source_annotation_count"] == 1
        assert manifest["reviewer"] == "reviewer-a"
        assert manifest["status"] == "COMPLETED"
        assert manifest["residual_pii_scan"]["status"] == "PASSED"
        assert item.residual_scan_status == "PASSED"
        assert manifest["processing_ms"] >= 0
        assert manifest["segments"][0]["label"] == "face"
        assert manifest["segments"][0]["mask"]["encoding"] == "bbox-fallback"
        assert "-filter_complex" in processor.command
        assert processor.command[processor.command.index("-map_metadata") + 1] == "-1"
        assert processor.command[processor.command.index("-map_chapters") + 1] == "-1"


def test_residual_pii_blocks_release_and_records_findings(tmp_path):
    Session = make_database()
    storage = LocalStorage(tmp_path)
    with Session() as session:
        video = Video(
            filename="ride.mp4",
            storage_path="videos/ride.mp4",
            file_size=10,
            duration_ms=1000,
            width=320,
            height=180,
            sample_fps=1,
        )
        frame = Frame(video=video, frame_number=1, timestamp_ms=0, storage_path="frames/1.jpg")
        task = AnnotationTask(video=video, status="COMPLETED")
        annotation = Annotation(
            task=task,
            frame=frame,
            label="face",
            annotation_type="bbox",
            geometry={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        )
        item = SanitizedExport(video=video, task=task, status="QUEUED", labels=["face"])
        job = ProcessingJob(
            video=video,
            sanitized_export=item,
            job_type="PII_SANITIZATION",
            state="SANITIZING_VIDEO",
        )
        session.add_all([video, frame, task, annotation, item, job])
        session.commit()
        source = storage.absolute_path(video.storage_path)
        source.parent.mkdir(parents=True)
        source.write_bytes(b"source")
        finding = PredictionOutput(
            label="face",
            confidence=0.82,
            annotation_type="bbox",
            geometry={"x": 0.4, "y": 0.2, "width": 0.1, "height": 0.1},
        )

        process_sanitization_job(
            session,
            job.id,
            processor=FakeSanitizationProcessor(),
            storage=storage,
            residual_provider=FakeResidualProvider([finding]),
        )
        session.refresh(item)
        session.refresh(job)
        manifest = json.loads(storage.absolute_path(item.manifest_path).read_text())

        assert item.status == "FAILED"
        assert item.error_code == "RESIDUAL_PII_DETECTED"
        assert item.storage_path is None
        assert item.residual_findings == 1
        assert job.state == "FAILED"
        assert manifest["residual_pii_scan"]["findings"][0]["label"] == "face"

        covered_scan = SanitizedExport(video=video, task=task, status="QUEUED", labels=["face"])
        covered_scan_job = ProcessingJob(
            video=video,
            sanitized_export=covered_scan,
            job_type="PII_SANITIZATION",
            state="SANITIZING_VIDEO",
        )
        session.add_all([covered_scan, covered_scan_job])
        session.commit()
        covered_finding = PredictionOutput(
            label="face",
            confidence=0.88,
            annotation_type="bbox",
            geometry={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        )
        process_sanitization_job(
            session,
            covered_scan_job.id,
            processor=FakeSanitizationProcessor(),
            storage=storage,
            residual_provider=FakeResidualProvider([covered_finding]),
        )
        session.refresh(covered_scan)
        covered_manifest = json.loads(
            storage.absolute_path(covered_scan.manifest_path).read_text()
        )

        assert covered_scan.status == "COMPLETED"
        assert covered_scan.residual_findings == 0
        assert covered_manifest["residual_pii_scan"]["covered_redetection_count"] == 1

        failed_scan = SanitizedExport(video=video, task=task, status="QUEUED", labels=["face"])
        failed_scan_job = ProcessingJob(
            video=video,
            sanitized_export=failed_scan,
            job_type="PII_SANITIZATION",
            state="SANITIZING_VIDEO",
        )
        session.add_all([failed_scan, failed_scan_job])
        session.commit()
        process_sanitization_job(
            session,
            failed_scan_job.id,
            processor=FakeSanitizationProcessor(),
            storage=storage,
            residual_provider=BrokenResidualProvider(),
        )
        session.refresh(failed_scan)
        failed_manifest = json.loads(
            storage.absolute_path(failed_scan.manifest_path).read_text()
        )

        assert failed_scan.status == "FAILED"
        assert failed_scan.error_code == "RESIDUAL_SCAN_FAILED"
        assert failed_scan.storage_path is None
        assert failed_manifest["residual_pii_scan"]["provider"] == "grounding-dino"
        assert len(failed_manifest["residual_pii_scan"]["model_revision"]) == 40


def test_sanitization_failure_writes_audit_manifest(tmp_path):
    Session = make_database()
    storage = LocalStorage(tmp_path)
    with Session() as session:
        video = Video(filename="ride.mp4", storage_path="videos/ride.mp4", file_size=10)
        task = AnnotationTask(video=video, status="COMPLETED")
        item = SanitizedExport(
            video=video,
            task=task,
            status="RUNNING",
            labels=["face"],
            reviewer="reviewer-a",
        )
        job = ProcessingJob(
            video=video,
            sanitized_export=item,
            job_type="PII_SANITIZATION",
            state="SANITIZING_VIDEO",
        )
        session.add_all([video, task, item, job])
        session.commit()

        record_sanitization_failure(
            session, job.id, "SANITIZATION_FAILED", "ffmpeg failed", storage
        )
        session.refresh(item)
        manifest = json.loads(storage.absolute_path(item.manifest_path).read_text())

        assert item.status == "FAILED"
        assert manifest["status"] == "FAILED"
        assert manifest["reviewer"] == "reviewer-a"
        assert manifest["error_code"] == "SANITIZATION_FAILED"
