import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_session
from app.models import (
    Annotation,
    AnnotationPropagation,
    AnnotationTask,
    Frame,
    ModelPrediction,
    ModelRun,
    PredictionDecision,
    Video,
)
from app.propagation import apply_bbox_delta, bbox_delta


def make_database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_bbox_delta_is_applied_and_clamped():
    delta = bbox_delta(
        {"x": 0.2, "y": 0.2, "width": 0.3, "height": 0.4},
        {"x": 0.3, "y": 0.1, "width": 0.4, "height": 0.5},
    )
    propagated = apply_bbox_delta(
        {"x": 0.7, "y": 0.7, "width": 0.3, "height": 0.3}, delta
    )

    assert propagated == pytest.approx(
        {"x": 0.6, "y": 0.6, "width": 0.4, "height": 0.4}
    )


def test_propagate_corrected_box_across_track():
    Session = make_database()
    with Session() as session:
        video = Video(
            filename="action.mp4",
            storage_path="videos/propagation-action.mp4",
            file_size=10,
            status="READY_FOR_ANNOTATION",
        )
        frames = [
            Frame(
                video=video,
                frame_number=index,
                timestamp_ms=(index - 1) * 200,
                storage_path=f"frames/propagation-action/{index}.jpg",
            )
            for index in (1, 2, 3)
        ]
        task = AnnotationTask(video=video, status="PENDING")
        model_run = ModelRun(
            video=video,
            model_kind="detection",
            provider="fake",
            model_name="detector",
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
                confidence=0.9,
                annotation_type="bbox",
                geometry={"x": 0.1 * index, "y": 0.2, "width": 0.3, "height": 0.5},
                track_id="7",
            )
            for index, frame in enumerate(frames, start=1)
        ]
        session.add_all([video, *frames, task, model_run, *predictions])
        session.commit()
        task_id = task.id
        source_prediction_id = predictions[1].id

    def test_session():
        with Session() as session:
            yield session

    main.app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(main.app) as client:
            response = client.post(
                f"/api/predictions/{source_prediction_id}/propagate",
                json={
                    "task_id": task_id,
                    "start_frame_number": 1,
                    "end_frame_number": 3,
                    "geometry": {"x": 0.25, "y": 0.18, "width": 0.35, "height": 0.5},
                    "reviewer": "reviewer-a",
                    "duration_ms": 900,
                },
            )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["generated_count"] == 3
    assert payload["corrected"] is True
    assert payload["track_id"] == "7"
    with Session() as session:
        annotations = list(
            session.scalars(select(Annotation).order_by(Annotation.frame_id)).all()
        )
        propagation = session.scalar(select(AnnotationPropagation))
        decisions = list(session.scalars(select(PredictionDecision)).all())
        persisted_predictions = list(session.scalars(select(ModelPrediction)).all())

        assert len(annotations) == 3
        assert {annotation.source for annotation in annotations} == {"track_propagated"}
        assert {annotation.propagation_id for annotation in annotations} == {propagation.id}
        first = next(annotation for annotation in annotations if annotation.frame.frame_number == 1)
        assert first.geometry["x"] == 0.15
        assert propagation.correction_delta["x"] == pytest.approx(0.05)
        assert propagation.reviewer == "reviewer-a"
        assert {decision.action for decision in decisions} == {"PROPAGATED_CORRECTION"}
        assert {prediction.status for prediction in persisted_predictions} == {"CORRECTED"}


def test_propagation_rejects_untracked_prediction():
    Session = make_database()
    with Session() as session:
        video = Video(
            filename="action.mp4",
            storage_path="videos/untracked-action.mp4",
            file_size=10,
            status="READY_FOR_ANNOTATION",
        )
        frame = Frame(
            video=video,
            frame_number=1,
            timestamp_ms=0,
            storage_path="frames/untracked-action/1.jpg",
        )
        task = AnnotationTask(video=video)
        model_run = ModelRun(
            video=video,
            model_kind="detection",
            provider="fake",
            model_name="detector",
            model_version="v1",
            device="cpu",
            parameters={},
            status="COMPLETED",
        )
        prediction = ModelPrediction(
            model_run=model_run,
            frame=frame,
            label="person",
            confidence=0.9,
            annotation_type="bbox",
            geometry={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.5},
        )
        session.add_all([video, frame, task, model_run, prediction])
        session.commit()
        task_id, prediction_id = task.id, prediction.id

    def test_session():
        with Session() as session:
            yield session

    main.app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(main.app) as client:
            response = client.post(
                f"/api/predictions/{prediction_id}/propagate",
                json={
                    "task_id": task_id,
                    "start_frame_number": 1,
                    "end_frame_number": 1,
                    "geometry": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.5},
                },
            )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 409
