import io
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.api import exports
from app.database import Base, get_session
from app.models import Annotation, AnnotationTask, Frame, SanitizedExport, Video
from app.storage import LocalStorage


def make_database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_coco_yolo_and_sanitized_bundle_exports(tmp_path):
    Session = make_database()
    export_storage = LocalStorage(tmp_path)
    exports.storage = export_storage
    with Session() as session:
        video = Video(
            filename="ride.mp4",
            storage_path="videos/ride.mp4",
            file_size=10,
            width=640,
            height=360,
            status="READY_FOR_ANNOTATION",
        )
        frame = Frame(
            video=video,
            frame_number=1,
            timestamp_ms=0,
            storage_path="frames/ride/1.jpg",
            width=640,
            height=360,
        )
        task = AnnotationTask(video=video, status="COMPLETED")
        annotation = Annotation(
            task=task,
            frame=frame,
            label="face",
            annotation_type="bbox",
            geometry={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        )
        item = SanitizedExport(
            video=video,
            task=task,
            status="COMPLETED",
            labels=["face"],
            storage_path="sanitized/export/sanitized.mp4",
            manifest_path="sanitized/export/manifest.json",
        )
        session.add_all([video, frame, task, annotation, item])
        session.commit()
        task_id, export_id = task.id, item.id
    video_path = export_storage.absolute_path("sanitized/export/sanitized.mp4")
    manifest_path = export_storage.absolute_path("sanitized/export/manifest.json")
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"video")
    manifest_path.write_text("{}")

    def test_session():
        with Session() as session:
            yield session

    main.app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(main.app) as client:
            coco = client.get(f"/api/annotation-tasks/{task_id}/exports/coco")
            yolo = client.get(f"/api/annotation-tasks/{task_id}/exports/yolo")
            bundle = client.get(f"/api/sanitized-exports/{export_id}/bundle")
            request_id = client.get("/api/health", headers={"X-Request-ID": "trace-123"})
    finally:
        main.app.dependency_overrides.clear()

    assert coco.status_code == 200
    assert coco.json()["annotations"][0]["bbox"] == [64.0, 72.0, 192.0, 144.0]
    with zipfile.ZipFile(io.BytesIO(yolo.content)) as archive:
        assert archive.read("classes.txt") == b"face\n"
        assert archive.read("labels/1.txt").startswith(b"0 0.250000 0.400000")
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert set(archive.namelist()) == {"sanitized.mp4", "manifest.json"}
    assert request_id.headers["X-Request-ID"] == "trace-123"
