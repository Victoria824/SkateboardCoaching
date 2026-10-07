from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.api import uploads
from app.database import Base, get_session
from app.models import DirectUpload, ProcessingJob, Video
from app.storage import S3BackedStorage, S3ObjectStore


class FakeObjectStore:
    def __init__(self):
        self.objects = {}
        self.presigned = []

    def presign_put(self, key, content_type, sha256, expires_in=None):
        self.presigned.append((key, content_type, sha256))
        return "https://objects.test/upload/{}".format(key)

    def presign_get(self, key, expires_in=None):
        return "https://objects.test/download/{}".format(key)

    def head(self, key):
        payload = self.objects[key]
        return {
            "ContentLength": len(payload["body"]),
            "Metadata": {"sha256": payload["sha256"]},
        }

    def upload(self, path: Path, key: str, content_type=None):
        self.objects[key] = {"body": path.read_bytes(), "sha256": "server-artifact"}

    def download(self, key: str, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.objects[key]["body"])


class FakeSigningClient:
    def __init__(self, origin):
        self.origin = origin

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return "{}/{}/{}".format(self.origin, operation, Params["Key"])


def make_database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_s3_backed_storage_materializes_persists_and_presigns(tmp_path):
    object_store = FakeObjectStore()
    object_store.objects["videos/source.mp4"] = {"body": b"source", "sha256": "a" * 64}
    storage = S3BackedStorage(tmp_path, object_store=object_store)

    materialized = storage.absolute_path("videos/source.mp4")
    assert materialized.read_bytes() == b"source"
    artifact = tmp_path / "sanitized" / "result.mp4"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"result")
    assert storage.persist(artifact, "video/mp4") == "sanitized/result.mp4"
    assert object_store.objects["sanitized/result.mp4"]["body"] == b"result"
    assert storage.public_url("sanitized/result.mp4").endswith("sanitized/result.mp4")


def test_s3_presigning_uses_browser_reachable_client():
    store = S3ObjectStore(
        client=FakeSigningClient("http://minio:9000"),
        presign_client=FakeSigningClient("http://localhost:9000"),
    )
    assert store.presign_get("frames/1.jpg").startswith("http://localhost:9000")


def test_signed_direct_upload_creates_checksum_guarded_video_job(monkeypatch):
    Session = make_database()
    object_store = FakeObjectStore()
    checksum = "b" * 64
    monkeypatch.setattr(
        uploads,
        "settings",
        SimpleNamespace(
            storage_backend="s3",
            max_upload_bytes=1000,
            s3_presign_ttl_seconds=900,
        ),
    )
    monkeypatch.setattr(uploads, "get_object_store", lambda: object_store)

    def test_session():
        with Session() as session:
            yield session

    main.app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(main.app) as client:
            initiated = client.post(
                "/api/direct-uploads",
                json={
                    "filename": "ride.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 6,
                    "sha256": checksum,
                    "sampling_profile": "action",
                },
            )
            object_key = initiated.json()["object_key"]
            object_store.objects[object_key] = {"body": b"source", "sha256": checksum}
            completed = client.post(
                "/api/direct-uploads/{}/complete".format(initiated.json()["upload_id"])
            )
    finally:
        main.app.dependency_overrides.clear()

    assert initiated.status_code == 201
    assert initiated.json()["required_headers"]["x-amz-meta-sha256"] == checksum
    assert completed.status_code == 202
    assert completed.json()["video"]["sample_fps"] == 5
    with Session() as session:
        video = session.query(Video).one()
        job = session.query(ProcessingJob).one()
        direct = session.query(DirectUpload).one()
        assert video.storage_path == object_key
        assert video.source_sha256 == checksum
        assert job.state == "QUEUED"
        assert direct.status == "COMPLETED"
