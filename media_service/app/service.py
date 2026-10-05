import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .config import settings
from .inference import InferenceError, PredictionProvider, UltralyticsProvider
from .media import FFmpegProcessor, MediaProcessingError
from .models import Frame, ModelPrediction, ModelRun, ProcessingJob, Video
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

    claimed_state = "RUNNING_INFERENCE" if candidate.job_type == "MODEL_INFERENCE" else "PROCESSING_VIDEO"
    result = session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == candidate.id,
            ProcessingJob.state.in_(("QUEUED", "RETRY_PENDING")),
        )
        .values(
            state=claimed_state,
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


def record_inference_failure(session: Session, job_id: str, code: str, message: str) -> None:
    session.rollback()
    job = session.get(ProcessingJob, job_id)
    model_run = session.get(ModelRun, job.model_run_id) if job and job.model_run_id else None
    if job:
        job.error_code = code
        job.error_message = message[-2000:]
        job.state = "RETRY_PENDING" if job.attempts < job.max_attempts else "FAILED"
        job.progress = 0
    if model_run:
        model_run.status = "RETRY_PENDING" if job and job.state == "RETRY_PENDING" else "FAILED"
        model_run.error_code = code
        model_run.error_message = message[-2000:]
    session.commit()


def process_inference_job(
    session: Session,
    job_id: str,
    provider: Optional[PredictionProvider] = None,
    storage: Optional[LocalStorage] = None,
) -> None:
    storage = storage or LocalStorage()
    job = session.get(ProcessingJob, job_id)
    if job is None or job.model_run_id is None:
        raise ValueError("Inference job is missing its model run")
    model_run = session.get(ModelRun, job.model_run_id)
    if model_run is None:
        raise ValueError("Unknown model run {}".format(job.model_run_id))

    try:
        provider = provider or UltralyticsProvider(model_run.model_name)
        model_run.status = "RUNNING"
        model_run.started_at = datetime.utcnow()
        model_run.total_frames = len(model_run.video.frames)
        model_run.processed_frames = 0
        model_run.error_code = None
        model_run.error_message = None
        job.state = "RUNNING_INFERENCE"
        job.progress = 5
        session.execute(delete(ModelPrediction).where(ModelPrediction.model_run_id == model_run.id))
        session.commit()

        started_at = datetime.utcnow()
        threshold = float(model_run.parameters.get("confidence_threshold", 0.25))
        frames = list(model_run.video.frames)
        for index, frame in enumerate(frames, start=1):
            outputs = provider.infer_frame(
                storage.absolute_path(frame.storage_path),
                model_run.model_kind,
                threshold,
                model_run.device,
            )
            for output in outputs:
                session.add(
                    ModelPrediction(
                        model_run_id=model_run.id,
                        frame_id=frame.id,
                        label=output.label,
                        confidence=output.confidence,
                        annotation_type=output.annotation_type,
                        geometry=output.geometry,
                    )
                )
            model_run.processed_frames = index
            job.progress = 5 + round((index / max(1, len(frames))) * 90)
            session.commit()

        completed_at = datetime.utcnow()
        model_run.model_version = "{}+ultralytics-{}".format(
            model_run.model_version, provider.runtime_version
        )
        model_run.latency_ms = round((completed_at - started_at).total_seconds() * 1000)
        model_run.status = "COMPLETED"
        model_run.completed_at = completed_at
        job.state = "COMPLETED"
        job.progress = 100
        job.completed_at = completed_at
        session.commit()
    except InferenceError as error:
        record_inference_failure(session, job_id, error.code, str(error))
        logger.exception("Model inference failed", extra={"job_id": job_id})
    except Exception as error:
        record_inference_failure(session, job_id, "UNEXPECTED_INFERENCE_ERROR", str(error))
        logger.exception("Unexpected inference failure", extra={"job_id": job_id})
