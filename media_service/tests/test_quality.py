import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_session
from app.models import (
    Annotation,
    AnnotationActivity,
    AnnotationTask,
    Frame,
    ModelPrediction,
    ModelRun,
    Video,
)
from app.quality import bbox_iou, keypoint_pck, route_model_run_reviews


def make_database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_bbox_iou_and_keypoint_agreement():
    overlap = bbox_iou(
        {"x": 0, "y": 0, "width": 0.5, "height": 0.5},
        {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
    )
    score = keypoint_pck(
        {"points": [{"name": "head", "x": 0.1, "y": 0.1, "visible": True}]},
        {"points": [{"name": "head", "x": 0.12, "y": 0.12, "visible": True}]},
    )

    assert overlap == pytest.approx(1 / 7)
    assert score == 1


def test_review_routing_and_dataset_health_api():
    Session = make_database()
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
        tasks = [
            AnnotationTask(video=video, status="COMPLETED", assigned_to=name)
            for name in ("annotator-a", "annotator-b")
        ]
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
            label="rider",
            confidence=0.3,
            annotation_type="bbox",
            geometry={"x": 0, "y": 0.2, "width": 0.3, "height": 0.5},
        )
        session.add_all([video, frame, *tasks, model_run, prediction])
        session.flush()
        for task in tasks:
            session.add_all(
                [
                    Annotation(
                        task=task,
                        frame=frame,
                        label="rider",
                        annotation_type="bbox",
                        geometry={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.5},
                    ),
                    Annotation(
                        task=task,
                        frame=frame,
                        label="rider_pose",
                        annotation_type="keypoints",
                        geometry={
                            "points": [
                                {"name": "head", "x": 0.2, "y": 0.2, "visible": True}
                            ]
                        },
                    ),
                ]
            )
        session.add(
            AnnotationActivity(
                task=tasks[0],
                frame_id=frame.id,
                action="SAVE",
                duration_ms=1000,
                annotation_count=2,
            )
        )
        session.flush()
        created = route_model_run_reviews(session, model_run, audit_percentage=0)
        session.commit()
        video_id = video.id

    assert created == 2

    def test_session():
        with Session() as session:
            yield session

    main.app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(main.app) as client:
            reviews = client.get(f"/api/review-items?video_id={video_id}")
            review_id = reviews.json()[0]["id"]
            resolved = client.post(
                f"/api/review-items/{review_id}/resolve",
                json={"action": "APPROVED", "reviewer": "reviewer-a"},
            )
            health = client.get(f"/api/dataset-health?video_id={video_id}")
            agreement = client.get(f"/api/videos/{video_id}/agreement")
    finally:
        main.app.dependency_overrides.clear()

    assert reviews.status_code == 200
    assert {item["reason"] for item in reviews.json()} == {"LOW_CONFIDENCE", "EDGE_CLIPPED"}
    assert resolved.json()["status"] == "RESOLVED"
    assert health.status_code == 200
    assert health.json()["open_review_items"] == 1
    assert health.json()["resolved_review_items"] == 1
    assert health.json()["low_confidence_predictions"] == 1
    assert health.json()["agreement"]["mean_bbox_iou"] == 1
    assert health.json()["agreement"]["mean_keypoint_pck"] == 1
    assert agreement.json()["bbox_comparisons"] == 1


def test_force_new_annotation_task_supports_agreement_workflows():
    Session = make_database()
    with Session() as session:
        video = Video(
            filename="ride.mp4",
            storage_path="videos/ride.mp4",
            file_size=10,
            status="READY_FOR_ANNOTATION",
        )
        session.add(video)
        session.commit()
        video_id = video.id

    def test_session():
        with Session() as session:
            yield session

    main.app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(main.app) as client:
            first = client.post(
                f"/api/videos/{video_id}/annotation-tasks?assigned_to=annotator-a"
            )
            second = client.post(
                f"/api/videos/{video_id}/annotation-tasks?assigned_to=annotator-b&force_new=true"
            )
    finally:
        main.app.dependency_overrides.clear()

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert second.json()["assigned_to"] == "annotator-b"


def test_cross_model_review_routing_is_idempotent():
    Session = make_database()
    with Session() as session:
        video = Video(
            filename="ride.mp4",
            storage_path="videos/cross-model.mp4",
            file_size=10,
            status="READY_FOR_ANNOTATION",
        )
        frames = [
            Frame(
                video=video,
                frame_number=index,
                timestamp_ms=(index - 1) * 1000,
                storage_path=f"frames/cross-model/{index}.jpg",
            )
            for index in (1, 2)
        ]
        detection_run = ModelRun(
            video=video,
            model_kind="detection",
            provider="fake",
            model_name="detector",
            model_version="v1",
            device="cpu",
            parameters={},
            status="COMPLETED",
        )
        pose_run = ModelRun(
            video=video,
            model_kind="pose",
            provider="fake",
            model_name="pose",
            model_version="v1",
            device="cpu",
            parameters={},
            status="COMPLETED",
        )
        session.add_all(
            [
                video,
                *frames,
                detection_run,
                pose_run,
                ModelPrediction(
                    model_run=detection_run,
                    frame=frames[0],
                    label="rider",
                    confidence=0.9,
                    annotation_type="bbox",
                    geometry={"x": 0.2, "y": 0.2, "width": 0.3, "height": 0.5},
                ),
                ModelPrediction(
                    model_run=pose_run,
                    frame=frames[1],
                    label="rider_pose",
                    confidence=0.9,
                    annotation_type="keypoints",
                    geometry={
                        "points": [{"name": "head", "x": 0.3, "y": 0.2, "visible": True}]
                    },
                ),
            ]
        )
        session.flush()

        first_count = route_model_run_reviews(
            session, pose_run, low_confidence_threshold=0, audit_percentage=0
        )
        second_count = route_model_run_reviews(
            session, pose_run, low_confidence_threshold=0, audit_percentage=0
        )
        reasons = {item.reason for item in video.review_items}

    assert first_count == 2
    assert second_count == 0
    assert reasons == {"MISSING_POSE", "POSE_WITHOUT_RIDER"}


def test_temporal_and_association_review_routing():
    Session = make_database()
    with Session() as session:
        video = Video(
            filename="action.mp4",
            storage_path="videos/temporal-action.mp4",
            file_size=10,
            status="READY_FOR_ANNOTATION",
        )
        frames = [
            Frame(
                video=video,
                frame_number=index,
                timestamp_ms=(index - 1) * 200,
                storage_path=f"frames/temporal-action/{index}.jpg",
            )
            for index in (1, 2, 3)
        ]
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
                frame=frames[0],
                label="rider",
                confidence=0.9,
                annotation_type="bbox",
                geometry={"x": 0.2, "y": 0.2, "width": 0.3, "height": 0.5},
                track_id="7",
            ),
            ModelPrediction(
                model_run=model_run,
                frame=frames[2],
                label="rider",
                confidence=0.9,
                annotation_type="bbox",
                geometry={"x": 0.25, "y": 0.2, "width": 0.3, "height": 0.5},
                track_id="7",
            ),
            ModelPrediction(
                model_run=model_run,
                frame=frames[1],
                label="snowboard",
                confidence=0.9,
                annotation_type="bbox",
                geometry={"x": 0.2, "y": 0.72, "width": 0.35, "height": 0.08},
                track_id="12",
            ),
            ModelPrediction(
                model_run=model_run,
                frame=frames[1],
                label="snowboard",
                confidence=0.9,
                annotation_type="bbox",
                geometry={"x": 0.6, "y": 0.72, "width": 0.25, "height": 0.08},
                track_id="13",
                associated_prediction_id=None,
                association_score=0.45,
                association_ambiguous=True,
            ),
        ]
        session.add_all([video, *frames, model_run, *predictions])
        session.flush()

        created = route_model_run_reviews(
            session, model_run, low_confidence_threshold=0, audit_percentage=0
        )
        reasons = [item.reason for item in video.review_items]

    assert created == 4
    assert reasons.count("UNASSOCIATED_SNOWBOARD") == 2
    assert reasons.count("AMBIGUOUS_BOARD_ASSOCIATION") == 1
    assert reasons.count("TRACK_GAP") == 1
