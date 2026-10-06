import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_session
from app.models import Annotation, AnnotationTask, Frame, ProcessingJob, SanitizedExport, Video
from app.privacy import BlurSegment, build_ffmpeg_blur_filter
from app.service import claim_next_job, process_sanitization_job, record_sanitization_failure
from app.storage import LocalStorage


class FakeSanitizationProcessor:
    def __init__(self):
        self.command = None

    def _run(self, command, _):
        self.command = command
        Path(command[-1]).write_bytes(b"sanitized-video")


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
        process_sanitization_job(session, job_id, processor=processor, storage=storage)
        item = session.scalar(select(SanitizedExport))
        manifest = json.loads(storage.absolute_path(item.manifest_path).read_text())

        assert item.status == "COMPLETED"
        assert item.output_sha256
        assert manifest["source_annotation_count"] == 1
        assert manifest["reviewer"] == "reviewer-a"
        assert manifest["status"] == "COMPLETED"
        assert manifest["processing_ms"] >= 0
        assert manifest["segments"][0]["label"] == "face"
        assert manifest["segments"][0]["pixel_geometry"] == {
            "x": 64,
            "y": 72,
            "width": 128,
            "height": 108,
        }
        assert "-filter_complex" in processor.command
        assert processor.command[processor.command.index("-map_metadata") + 1] == "-1"
        assert processor.command[processor.command.index("-map_chapters") + 1] == "-1"


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
