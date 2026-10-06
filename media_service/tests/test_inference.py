from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_session
from app.inference import PredictionOutput
from app.models import (
    AnnotationTask,
    Frame,
    ModelPrediction,
    ModelRun,
    ProcessingJob,
    Video,
)
from app.service import claim_next_job, process_inference_job
from app.storage import LocalStorage


class FakeProvider:
    runtime_version = "test-runtime"

    def infer_frame(self, image_path: Path, model_kind: str, confidence_threshold: float, device: str):
        assert image_path.exists()
        assert model_kind == "detection"
        assert confidence_threshold == 0.3
        assert device == "cpu"
        return [
            PredictionOutput(
                label="rider",
                confidence=0.91,
                annotation_type="bbox",
                geometry={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.5},
            )
        ]


class FakeTrackedProvider:
    runtime_version = "tracked-runtime"

    def infer_frames(self, image_paths, model_kind, confidence_threshold, device):
        assert len(image_paths) == 2
        return [
            [
                PredictionOutput(
                    label="person",
                    confidence=0.95,
                    annotation_type="bbox",
                    geometry={"x": 0.2, "y": 0.1, "width": 0.3, "height": 0.6},
                    external_track_id=7,
                ),
                PredictionOutput(
                    label="snowboard",
                    confidence=0.88,
                    annotation_type="bbox",
                    geometry={"x": 0.18, "y": 0.68, "width": 0.38, "height": 0.08},
                    external_track_id=12,
                ),
            ],
            [
                PredictionOutput(
                    label="person",
                    confidence=0.93,
                    annotation_type="bbox",
                    geometry={"x": 0.22, "y": 0.1, "width": 0.3, "height": 0.6},
                    external_track_id=7,
                )
            ],
        ]


def make_database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_inference_worker_persists_versioned_predictions(tmp_path):
    Session = make_database()
    storage = LocalStorage(tmp_path)
    with Session() as session:
        video = Video(
            filename="ride.mp4",
            storage_path="videos/ride.mp4",
            file_size=10,
            status="READY_FOR_ANNOTATION",
        )
        frame = Frame(
            video=video,
            frame_number=1,
            timestamp_ms=0,
            storage_path="frames/ride/frame.jpg",
        )
        model_run = ModelRun(
            video=video,
            model_kind="detection",
            provider="fake",
            model_name="fake-detector",
            model_version="v1",
            device="cpu",
            parameters={"confidence_threshold": 0.3},
            status="QUEUED",
        )
        job = ProcessingJob(
            video=video,
            model_run=model_run,
            job_type="MODEL_INFERENCE",
            state="QUEUED",
        )
        session.add_all([video, frame, model_run, job])
        session.commit()
        frame_file = storage.absolute_path(frame.storage_path)
        frame_file.parent.mkdir(parents=True)
        frame_file.write_bytes(b"image")

        job_id = claim_next_job(session)
        process_inference_job(session, job_id, provider=FakeProvider(), storage=storage)

        session.refresh(job)
        session.refresh(model_run)
        assert job.state == "COMPLETED"
        assert model_run.status == "COMPLETED"
        assert model_run.model_version == "v1+ultralytics-test-runtime"
        assert model_run.processed_frames == 1
        assert len(model_run.predictions) == 1
        assert model_run.predictions[0].confidence == 0.91


def test_inference_worker_tracks_and_associates_rider_sequence(tmp_path):
    Session = make_database()
    storage = LocalStorage(tmp_path)
    with Session() as session:
        video = Video(
            filename="action.mp4",
            storage_path="videos/action.mp4",
            file_size=10,
            sampling_profile="action",
            sample_fps=5,
            status="READY_FOR_ANNOTATION",
        )
        frames = [
            Frame(
                video=video,
                frame_number=index,
                timestamp_ms=(index - 1) * 200,
                storage_path=f"frames/action/{index}.jpg",
            )
            for index in (1, 2)
        ]
        model_run = ModelRun(
            video=video,
            model_kind="detection",
            provider="fake",
            model_name="tracked-detector",
            model_version="v1",
            device="cpu",
            parameters={"confidence_threshold": 0.25},
            status="QUEUED",
        )
        job = ProcessingJob(
            video=video,
            model_run=model_run,
            job_type="MODEL_INFERENCE",
            state="QUEUED",
        )
        session.add_all([video, *frames, model_run, job])
        session.commit()
        for frame in frames:
            path = storage.absolute_path(frame.storage_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"image")

        process_inference_job(
            session,
            claim_next_job(session),
            provider=FakeTrackedProvider(),
            storage=storage,
        )

        session.refresh(model_run)
        people = sorted(
            (prediction for prediction in model_run.predictions if prediction.track_id == "7"),
            key=lambda prediction: prediction.frame.frame_number,
        )
        board = next(
            prediction for prediction in model_run.predictions if prediction.label == "snowboard"
        )
        assert [prediction.label for prediction in people] == ["rider", "rider"]
        assert board.associated_prediction_id == people[0].id
        assert people[0].associated_prediction_id == board.id
        assert board.association_score is not None and board.association_score >= 0.3
        assert model_run.parameters["tracker"] == "ByteTrack+geometry-fallback-v1"


def test_prediction_accept_correct_reject_and_metrics():
    Session = make_database()
    with Session() as session:
        video = Video(
            filename="ride.mp4",
            storage_path="videos/ride.mp4",
            file_size=10,
            status="READY_FOR_ANNOTATION",
        )
        frame = Frame(video=video, frame_number=1, timestamp_ms=0, storage_path="frames/1.jpg")
        task = AnnotationTask(video=video, status="PENDING")
        model_run = ModelRun(
            video=video,
            model_kind="detection",
            provider="fake",
            model_name="fake-detector",
            model_version="v1",
            device="cpu",
            parameters={},
            status="COMPLETED",
        )
        predictions = [
            ModelPrediction(
                model_run=model_run,
                frame=frame,
                label="rider",
                confidence=confidence,
                annotation_type="bbox",
                geometry={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.5},
            )
            for confidence in (0.9, 0.8, 0.7)
        ]
        session.add_all([video, frame, task, model_run, *predictions])
        session.commit()
        video_id, frame_id, task_id, run_id = video.id, frame.id, task.id, model_run.id
        prediction_ids = [prediction.id for prediction in predictions]

    def test_session():
        with Session() as session:
            yield session

    main.app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(main.app) as client:
            listed = client.get(f"/api/frames/{frame_id}/predictions")
            rejected = client.post(
                f"/api/predictions/{prediction_ids[2]}/reject",
                json={"task_id": task_id, "duration_ms": 300},
            )
            saved = client.put(
                f"/api/annotation-tasks/{task_id}/frames/{frame_id}/annotations",
                json={
                    "duration_ms": 600,
                    "annotations": [
                        {
                            "label": "rider",
                            "annotation_type": "bbox",
                            "geometry": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.5},
                            "source": "model",
                            "model_prediction_id": prediction_ids[0],
                        },
                        {
                            "label": "rider",
                            "annotation_type": "bbox",
                            "geometry": {"x": 0.2, "y": 0.2, "width": 0.3, "height": 0.5},
                            "source": "model_corrected",
                            "model_prediction_id": prediction_ids[1],
                        },
                    ],
                },
            )
            metrics = client.get(f"/api/model-runs/{run_id}/metrics")
            runs = client.get(f"/api/videos/{video_id}/model-runs")
            created_run = client.post(
                f"/api/videos/{video_id}/model-runs",
                json={"model_kind": "pose", "confidence_threshold": 0.4},
            )
    finally:
        main.app.dependency_overrides.clear()

    assert listed.status_code == 200
    assert listed.json()[0]["model_name"] == "fake-detector"
    assert rejected.json()["status"] == "REJECTED"
    assert saved.json()["saved_count"] == 2
    payload = metrics.json()
    assert payload["accepted"] == 1
    assert payload["corrected"] == 1
    assert payload["rejected"] == 1
    assert payload["acceptance_rate"] == 1 / 3
    assert payload["average_decision_time_ms"] == 500
    assert runs.status_code == 200
    assert runs.json()[0]["id"] == run_id
    assert created_run.status_code == 202
    assert created_run.json()["model_run"]["model_name"] == "yolo11n-pose.pt"
    assert created_run.json()["job"]["state"] == "QUEUED"
