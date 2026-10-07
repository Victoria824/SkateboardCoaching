from pathlib import Path
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.media import VideoMetadata
from app.dispatcher import publish_pending
from app.models import JobOutbox, ProcessingJob, Video
from app.service import claim_job_by_id, claim_next_job, process_job
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
        assert session.query(JobOutbox).filter_by(job_id=job.id).one().status == "PENDING"


def test_expired_worker_lease_is_reclaimed_once():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        video = Video(filename="ride.mp4", storage_path="videos/ride.mp4", file_size=5)
        job = ProcessingJob(
            video=video,
            state="PROCESSING_VIDEO",
            attempts=1,
            max_attempts=3,
            worker_id="dead-worker",
            lease_expires_at=datetime.utcnow() - timedelta(seconds=1),
        )
        session.add_all([video, job])
        session.commit()

        assert claim_next_job(session, worker_id="replacement-worker") == job.id
        session.refresh(job)
        assert job.attempts == 2
        assert job.worker_id == "replacement-worker"
        assert job.lease_expires_at > datetime.utcnow()


def test_exhausted_expired_lease_becomes_failed():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        video = Video(filename="ride.mp4", storage_path="videos/ride.mp4", file_size=5)
        job = ProcessingJob(
            video=video,
            state="PROCESSING_VIDEO",
            attempts=3,
            max_attempts=3,
            lease_expires_at=datetime.utcnow() - timedelta(seconds=1),
        )
        session.add_all([video, job])
        session.commit()

        assert claim_next_job(session, worker_id="replacement-worker") is None
        session.refresh(job)
        assert job.state == "FAILED"
        assert job.error_code == "WORKER_LEASE_EXPIRED"


def test_exact_celery_claim_marks_exhausted_expired_lease_failed():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        video = Video(filename="ride.mp4", storage_path="videos/ride.mp4", file_size=5)
        job = ProcessingJob(
            video=video,
            state="RUNNING_INFERENCE",
            job_type="MODEL_INFERENCE",
            attempts=3,
            max_attempts=3,
            lease_expires_at=datetime.utcnow() - timedelta(seconds=1),
        )
        session.add_all([video, job])
        session.commit()

        assert claim_job_by_id(session, job.id, "replacement-worker") is None
        session.refresh(job)
        assert job.state == "FAILED"
        assert job.error_code == "WORKER_LEASE_EXPIRED"


def test_worker_rejects_materialized_source_checksum_mismatch(tmp_path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    storage = LocalStorage(tmp_path)
    with Session() as session:
        video = Video(
            filename="ride.mp4",
            storage_path="videos/ride.mp4",
            file_size=5,
            source_sha256="a" * 64,
            status="QUEUED",
        )
        job = ProcessingJob(video=video, state="QUEUED")
        session.add_all([video, job])
        session.commit()
        source = storage.absolute_path(video.storage_path)
        source.parent.mkdir(parents=True)
        source.write_bytes(b"not-the-expected-file")

        process_job(
            session,
            claim_next_job(session, worker_id="checksum-worker"),
            processor=FakeProcessor(),
            storage=storage,
        )
        session.refresh(job)
        assert job.state == "RETRY_PENDING"
        assert job.error_code == "SOURCE_CHECKSUM_MISMATCH"


def test_transactional_outbox_publishes_and_duplicate_delivery_cannot_reclaim():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    delivered = []
    with Session() as session:
        video = Video(filename="ride.mp4", storage_path="videos/ride.mp4", file_size=5)
        job = ProcessingJob(video=video, state="QUEUED")
        session.add_all([video, job])
        session.commit()
        outbox = session.query(JobOutbox).one()

        assert outbox.job_id == job.id
        assert publish_pending(
            session, lambda job_id, event_id: delivered.append((job_id, event_id))
        ) == 1
        session.refresh(outbox)
        assert delivered == [(job.id, outbox.id)]
        assert outbox.status == "PUBLISHED"
        assert claim_job_by_id(session, job.id, "celery-worker-a") == job.id
        assert claim_job_by_id(session, job.id, "celery-worker-b") is None


def test_dispatcher_skips_pending_outbox_for_terminal_job():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        video = Video(filename="ride.mp4", storage_path="videos/ride.mp4", file_size=5)
        job = ProcessingJob(video=video, state="FAILED")
        session.add_all([video, job])
        session.commit()
        outbox = session.query(JobOutbox).filter_by(job_id=job.id).one()

        assert publish_pending(session, lambda *_: None) == 0
        session.refresh(outbox)
        assert outbox.status == "SKIPPED"
