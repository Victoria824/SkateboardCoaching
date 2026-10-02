import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .config import settings
from .media import FFmpegProcessor, MediaProcessingError
from .models import Frame, ProcessingJob, Video
from .storage import LocalStorage


logger = logging.getLogger(__name__)


def record_failure(session: Session, job_id: str, code: str, message: str) -> None:
    session.rollback()
    job = session.get(ProcessingJob, job_id)
    video = session.get(Video, job.video_id) if job else None
    if job:
        job.error_code = code
        job.error_message = message[-2000:]
        job.state = "RETRY_PENDING" if job.attempts < job.max_attempts else "FAILED"
        job.progress = 0
    if video:
        video.status = "PROCESSING_FAILED"
    session.commit()


def claim_next_job(session: Session) -> Optional[str]:
    candidate = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.state.in_(("QUEUED", "RETRY_PENDING")))
        .order_by(ProcessingJob.created_at)
        .limit(1)
    )
    if candidate is None:
        return None

    result = session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == candidate.id,
            ProcessingJob.state.in_(("QUEUED", "RETRY_PENDING")),
        )
        .values(
            state="PROCESSING_VIDEO",
            progress=5,
            attempts=ProcessingJob.attempts + 1,
            started_at=datetime.utcnow(),
            error_code=None,
            error_message=None,
        )
    )
    session.commit()
    return candidate.id if result.rowcount == 1 else None


def process_job(
    session: Session,
    job_id: str,
    processor: Optional[FFmpegProcessor] = None,
    storage: Optional[LocalStorage] = None,
) -> None:
    processor = processor or FFmpegProcessor()
    storage = storage or LocalStorage()
    job = session.get(ProcessingJob, job_id)
    if job is None:
        raise ValueError("Unknown job {}".format(job_id))
    video = session.get(Video, job.video_id)
    if video is None:
        raise ValueError("Job {} has no video".format(job_id))

    try:
        video.status = "PROCESSING_VIDEO"
        job.state = "PROCESSING_VIDEO"
        job.progress = 10
        session.commit()

        source = storage.absolute_path(video.storage_path)
        metadata = processor.probe(source)
        video.duration_ms = metadata.duration_ms
        video.fps = metadata.fps
        video.width = metadata.width
        video.height = metadata.height
        video.codec = metadata.codec
        video.source_frame_count = metadata.frame_count
        job.state = "EXTRACTING_FRAMES"
        job.progress = 35
        session.commit()

        frame_dir = storage.frame_directory(video.id)
        extracted = processor.extract_frames(source, frame_dir, settings.frame_sample_fps)

        session.execute(delete(Frame).where(Frame.video_id == video.id))
        for index, frame_path in enumerate(extracted, start=1):
            session.add(
                Frame(
                    video_id=video.id,
                    frame_number=index,
                    timestamp_ms=round(((index - 1) / settings.frame_sample_fps) * 1000),
                    storage_path=storage.relative_path(frame_path),
                    width=metadata.width,
                    height=metadata.height,
                )
            )

        video.status = "READY_FOR_ANNOTATION"
        job.state = "READY_FOR_ANNOTATION"
        job.progress = 100
        job.completed_at = datetime.utcnow()
        session.commit()
        logger.info("Processed video", extra={"video_id": video.id, "job_id": job.id})
    except MediaProcessingError as error:
        record_failure(session, job_id, error.code, str(error))
        logger.exception("Media processing failed", extra={"job_id": job_id})
    except Exception as error:
        record_failure(session, job_id, "UNEXPECTED_PROCESSING_ERROR", str(error))
        logger.exception("Unexpected media processing failure", extra={"job_id": job_id})
