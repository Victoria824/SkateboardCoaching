import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_session
from app.models import AnnotationActivity, Frame, Video


def test_annotation_task_and_frame_annotations(tmp_path):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        video = Video(
            filename="ride.mp4",
            storage_path="videos/ride.mp4",
            file_size=100,
            status="READY_FOR_ANNOTATION",
            duration_ms=2000,
            fps=30,
            width=640,
            height=360,
            codec="h264",
        )
        frame = Frame(
            video=video,
            frame_number=1,
            timestamp_ms=0,
            storage_path="frames/ride/frame-000001.jpg",
            width=640,
            height=360,
        )
        session.add_all([video, frame])
        session.commit()
        video_id, frame_id = video.id, frame.id

    def test_session():
        with Session() as session:
            yield session

    main.app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(main.app) as client:
            created = client.post(f"/api/videos/{video_id}/annotation-tasks")
            repeated = client.post(f"/api/videos/{video_id}/annotation-tasks")
            task_id = created.json()["id"]
            saved = client.put(
                f"/api/annotation-tasks/{task_id}/frames/{frame_id}/annotations",
                json={
                    "duration_ms": 1250,
                    "annotations": [
                        {
                            "label": "rider",
                            "annotation_type": "bbox",
                            "geometry": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.5},
                            "source": "human",
                        },
                        {
                            "label": "rider_pose",
                            "annotation_type": "keypoints",
                            "geometry": {
                                "points": [{"name": "head", "x": 0.25, "y": 0.3, "visible": True}]
                            },
                            "source": "human",
                        },
                    ],
                },
            )
            listed = client.get(
                f"/api/annotation-tasks/{task_id}/frames/{frame_id}/annotations"
            )
            detail = client.get(f"/api/annotation-tasks/{task_id}")
            completed = client.post(f"/api/annotation-tasks/{task_id}/complete")
    finally:
        main.app.dependency_overrides.clear()

    assert created.status_code == 201
    assert repeated.json()["id"] == task_id
    assert saved.status_code == 200
    assert saved.json()["saved_count"] == 2
    assert len(listed.json()) == 2
    assert detail.json()["status"] == "IN_PROGRESS"
    assert len(detail.json()["video"]["frames"]) == 1
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["completed_at"] is not None
    with Session() as session:
        activity = session.scalar(select(AnnotationActivity))
        assert activity.duration_ms == 1250
        assert activity.annotation_count == 2


def test_rejects_out_of_bounds_bbox():
    from app.schemas import AnnotationSaveRequest

    with pytest.raises(ValidationError, match="normalized"):
        AnnotationSaveRequest.model_validate(
            {
                "annotations": [
                    {
                        "label": "rider",
                        "annotation_type": "bbox",
                        "geometry": {"x": 0.8, "y": 0.2, "width": 0.3, "height": 0.5},
                    }
                ]
            }
        )


def test_validates_nonempty_pixel_mask_rle():
    from app.schemas import AnnotationSaveRequest

    request = AnnotationSaveRequest.model_validate(
        {
            "annotations": [
                {
                    "label": "face",
                    "annotation_type": "mask",
                    "geometry": {
                        "encoding": "row-major-rle-v1",
                        "width": 8,
                        "height": 8,
                        "rle": [18, 4, 4, 4, 4, 4, 26],
                        "bbox": {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.375},
                        "edit_count": 2,
                        "last_edit": "paint",
                    },
                }
            ]
        }
    )

    assert request.annotations[0].annotation_type == "mask"
    with pytest.raises(ValidationError, match="cannot be empty"):
        AnnotationSaveRequest.model_validate(
            {
                "annotations": [
                    {
                        "label": "face",
                        "annotation_type": "mask",
                        "geometry": {
                            "encoding": "row-major-rle-v1",
                            "width": 8,
                            "height": 8,
                            "rle": [64],
                            "bbox": {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.375},
                        },
                    }
                ]
            }
        )
