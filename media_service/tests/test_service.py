from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.media import VideoMetadata
from app.models import ProcessingJob, Video
from app.service import claim_next_job, process_job
from app.storage import LocalStorage


class FakeProcessor:
    def __init__(self):
        self.sample_fps = None

    def probe(self, _: Path) -> VideoMetadata:
        return VideoMetadata(
            duration_ms=2000,
            fps=30.0,
            width=1280,
            height=720,
            codec="h264",
            frame_count=60,
        )

    def extract_frames(self, _: Path, output_dir: Path, sample_fps: float):
        assert sample_fps > 0
        self.sample_fps = sample_fps
        output_dir.mkdir(parents=True, exist_ok=True)
        frames = [output_dir / "frame-000001.jpg", output_dir / "frame-000002.jpg"]
        for frame in frames:
            frame.write_bytes(b"jpeg")
        return frames


class BrokenProcessor:
    def probe(self, _: Path) -> VideoMetadata:
        raise OSError("disk unavailable")


def test_worker_processes_a_queued_video(tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    storage = LocalStorage(tmp_path)

    with Session() as session:
        video = Video(
            filename="ride.mp4",
            storage_path="videos/video/ride.mp4",
            file_size=5,
            sampling_profile="action",
            sample_fps=5,
            status="QUEUED",
        )
        session.add(video)
        session.flush()
        source = storage.absolute_path(video.storage_path)
        source.parent.mkdir(parents=True)
        source.write_bytes(b"video")
        job = ProcessingJob(video=video, state="QUEUED")
        session.add(job)
        session.commit()

        claimed_id = claim_next_job(session)
        assert claimed_id == job.id

        processor = FakeProcessor()
        process_job(session, job.id, processor=processor, storage=storage)

        session.refresh(video)
        session.refresh(job)
        assert video.status == "READY_FOR_ANNOTATION"
        assert job.state == "READY_FOR_ANNOTATION"
        assert job.progress == 100
        assert len(video.frames) == 2
        assert processor.sample_fps == 5
        assert video.frames[1].timestamp_ms == 200


def test_worker_records_unexpected_failures_for_retry(tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    storage = LocalStorage(tmp_path)

    with Session() as session:
        video = Video(filename="ride.mp4", storage_path="videos/video/ride.mp4", file_size=5, status="QUEUED")
        session.add(video)
        session.flush()
        source = storage.absolute_path(video.storage_path)
        source.parent.mkdir(parents=True)
        source.write_bytes(b"video")
        job = ProcessingJob(video=video, state="QUEUED")
        session.add(job)
        session.commit()

        claimed_id = claim_next_job(session)
        process_job(session, claimed_id, processor=BrokenProcessor(), storage=storage)

        session.refresh(video)
        session.refresh(job)
        assert video.status == "PROCESSING_FAILED"
        assert job.state == "RETRY_PENDING"
        assert job.error_code == "UNEXPECTED_PROCESSING_ERROR"
        assert job.error_message == "disk unavailable"
