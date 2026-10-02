from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_session
from app.storage import LocalStorage


def test_upload_returns_accepted_job_and_supports_idempotency(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session():
        with Session() as session:
            yield session

    original_storage = main.storage
    main.storage = LocalStorage(tmp_path)
    main.app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(main.app) as client:
            first = client.post(
                "/api/videos",
                headers={"Idempotency-Key": "upload-one"},
                files={"video": ("ride.mp4", b"test-video", "video/mp4")},
            )
            second = client.post(
                "/api/videos",
                headers={"Idempotency-Key": "upload-one"},
                files={"video": ("ride.mp4", b"different", "video/mp4")},
            )
    finally:
        main.storage = original_storage
        main.app.dependency_overrides.clear()

    assert first.status_code == 202
    assert first.headers["location"].startswith("/api/jobs/")
    payload = first.json()
    assert payload["video"]["status"] == "QUEUED"
    assert payload["video"]["file_size"] == len(b"test-video")
    assert payload["job"]["state"] == "QUEUED"
    assert second.status_code == 202
    assert second.json()["job"]["id"] == payload["job"]["id"]
    stored_files = list(Path(tmp_path).glob("videos/*/ride.mp4"))
    assert len(stored_files) == 1


def test_upload_rejects_non_video_extension(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def test_session():
        with Session() as session:
            yield session

    original_storage = main.storage
    main.storage = LocalStorage(tmp_path)
    main.app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(main.app) as client:
            response = client.post(
                "/api/videos",
                files={"video": ("notes.txt", b"not-video", "text/plain")},
            )
    finally:
        main.storage = original_storage
        main.app.dependency_overrides.clear()

    assert response.status_code == 415

