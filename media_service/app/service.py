import json
import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session

from .config import settings
from .inference import (
    create_residual_pii_provider,
    InferenceError,
    OpenCVPIIProvider,
    PredictionOutput,
    PredictionProvider,
    UltralyticsProvider,
)
from .media import FFmpegProcessor, MediaProcessingError
from .models import (
    Annotation,
    Frame,
    JobOutbox,
    ModelPrediction,
    ModelRun,
    ProcessingJob,
    SanitizedExport,
    Video,
)
from .privacy import (
    build_ffmpeg_mask_filter,
    build_mask_segments,
    mask_segment_manifest,
    sha256_file,
)
from .quality import route_model_run_reviews
from .storage import LocalStorage, create_storage
from .tracking import associate_people_and_boards


logger = logging.getLogger(__name__)
ACTIVE_JOB_STATES = {
    "PROCESSING_VIDEO",
    "EXTRACTING_FRAMES",
    "RUNNING_INFERENCE",
    "SANITIZING_VIDEO",
}


def renew_job_lease(job: ProcessingJob) -> None:
    now = datetime.utcnow()
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=settings.worker_lease_seconds)


def requeue_job_outbox(session: Session, job: ProcessingJob) -> None:
    """Make a retry visible to the Celery dispatcher without creating duplicate rows."""
    outbox = session.scalar(select(JobOutbox).where(JobOutbox.job_id == job.id))
    if outbox is None:
        outbox = JobOutbox(job_id=job.id)
        session.add(outbox)
    else:
        outbox.status = "PENDING"
        outbox.published_at = None
        outbox.last_error = None


def mark_expired_job_failed(job: ProcessingJob) -> None:
    job.state = "FAILED"
    job.error_code = "WORKER_LEASE_EXPIRED"
    job.error_message = "Worker lease expired after maximum attempts"
    job.lease_expires_at = None
    if job.job_type == "VIDEO_INGESTION":
        job.video.status = "PROCESSING_FAILED"
    if job.model_run:
        job.model_run.status = "FAILED"
        job.model_run.error_code = job.error_code
        job.model_run.error_message = job.error_message
    if job.sanitized_export:
        job.sanitized_export.status = "FAILED"
        job.sanitized_export.error_code = job.error_code
        job.sanitized_export.error_message = job.error_message


def record_failure(session: Session, job_id: str, code: str, message: str) -> None:
    session.rollback()
    job = session.get(ProcessingJob, job_id)
    video = session.get(Video, job.video_id) if job else None
    if job:
        job.error_code = code
        job.error_message = message[-2000:]
        job.state = "RETRY_PENDING" if job.attempts < job.max_attempts else "FAILED"
        job.progress = 0
        job.lease_expires_at = None
    if video:
        video.status = "PROCESSING_FAILED"
    if job and job.state == "RETRY_PENDING":
        requeue_job_outbox(session, job)
    session.commit()


def claim_next_job(session: Session, worker_id: Optional[str] = None) -> Optional[str]:
    now = datetime.utcnow()
    worker_id = worker_id or "pid-{}".format(os.getpid())
    stale_lease = or_(
        ProcessingJob.lease_expires_at.is_(None), ProcessingJob.lease_expires_at < now
    )
    exhausted = list(
        session.scalars(
            select(ProcessingJob).where(
                ProcessingJob.state.in_(ACTIVE_JOB_STATES),
                stale_lease,
                ProcessingJob.attempts >= ProcessingJob.max_attempts,
            )
        ).all()
    )
    for job in exhausted:
        mark_expired_job_failed(job)
    if exhausted:
        session.commit()
    candidate = session.scalar(
        select(ProcessingJob)
        .where(
            or_(
                ProcessingJob.state.in_(("QUEUED", "RETRY_PENDING")),
                and_(
                    ProcessingJob.state.in_(ACTIVE_JOB_STATES),
                    stale_lease,
                    ProcessingJob.attempts < ProcessingJob.max_attempts,
                ),
            )
        )
        .order_by(ProcessingJob.created_at)
        .limit(1)
    )
    if candidate is None:
        return None

    claimed_state = {
        "MODEL_INFERENCE": "RUNNING_INFERENCE",
        "PII_SANITIZATION": "SANITIZING_VIDEO",
    }.get(candidate.job_type, "PROCESSING_VIDEO")
    result = session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == candidate.id,
            or_(
                ProcessingJob.state.in_(("QUEUED", "RETRY_PENDING")),
                and_(
                    ProcessingJob.state.in_(ACTIVE_JOB_STATES),
                    stale_lease,
                ),
            ),
        )
        .values(
            state=claimed_state,
            progress=5,
            attempts=ProcessingJob.attempts + 1,
            started_at=datetime.utcnow(),
            error_code=None,
            error_message=None,
            worker_id=worker_id,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=settings.worker_lease_seconds),
        )
    )
    session.commit()
    return candidate.id if result.rowcount == 1 else None


def claim_job_by_id(session: Session, job_id: str, worker_id: str) -> Optional[str]:
    """Idempotently claim the exact job named by an at-least-once queue message."""
    now = datetime.utcnow()
    stale_lease = or_(
        ProcessingJob.lease_expires_at.is_(None), ProcessingJob.lease_expires_at < now
    )
    candidate = session.get(ProcessingJob, job_id)
    if candidate is None:
        return None
    if candidate.attempts >= candidate.max_attempts:
        if candidate.state in ACTIVE_JOB_STATES and (
            candidate.lease_expires_at is None or candidate.lease_expires_at < now
        ):
            mark_expired_job_failed(candidate)
            session.commit()
        return None
    claimed_state = {
        "MODEL_INFERENCE": "RUNNING_INFERENCE",
        "PII_SANITIZATION": "SANITIZING_VIDEO",
    }.get(candidate.job_type, "PROCESSING_VIDEO")
    result = session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            or_(
                ProcessingJob.state.in_(("QUEUED", "RETRY_PENDING")),
                and_(ProcessingJob.state.in_(ACTIVE_JOB_STATES), stale_lease),
            ),
        )
        .values(
            state=claimed_state,
            progress=5,
            attempts=ProcessingJob.attempts + 1,
            started_at=now,
            error_code=None,
            error_message=None,
            worker_id=worker_id,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=settings.worker_lease_seconds),
        )
    )
    session.commit()
    return job_id if result.rowcount == 1 else None


def process_claimed_job(session: Session, job_id: str) -> None:
    job = session.get(ProcessingJob, job_id)
    if job is None:
        return
    if job.job_type == "MODEL_INFERENCE":
        process_inference_job(session, job_id)
    elif job.job_type == "PII_SANITIZATION":
        process_sanitization_job(session, job_id)
    else:
        process_job(session, job_id)


def process_job(
    session: Session,
    job_id: str,
    processor: Optional[FFmpegProcessor] = None,
    storage: Optional[LocalStorage] = None,
) -> None:
    processor = processor or FFmpegProcessor()
    storage = storage or create_storage()
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
        renew_job_lease(job)
        session.commit()

        source = storage.absolute_path(video.storage_path)
        if video.source_sha256 and sha256_file(source) != video.source_sha256:
            raise MediaProcessingError(
                "SOURCE_CHECKSUM_MISMATCH", "Materialized source does not match upload checksum"
            )
        metadata = processor.probe(source)
        video.duration_ms = metadata.duration_ms
        video.fps = metadata.fps
        video.width = metadata.width
        video.height = metadata.height
        video.codec = metadata.codec
        video.source_frame_count = metadata.frame_count
        job.state = "EXTRACTING_FRAMES"
        job.progress = 35
        renew_job_lease(job)
        session.commit()

        frame_dir = storage.frame_directory(video.id)
        sample_fps = video.sample_fps or settings.frame_sample_fps
        if video.sampling_profile == "motion":
            extracted = processor.extract_motion_aware_frames(source, frame_dir)
        else:
            extracted = processor.extract_frames(source, frame_dir, sample_fps)

        session.execute(delete(Frame).where(Frame.video_id == video.id))
        for index, extracted_frame in enumerate(extracted, start=1):
            frame_path = getattr(extracted_frame, "path", extracted_frame)
            timestamp_ms = getattr(
                extracted_frame,
                "timestamp_ms",
                round(((index - 1) / sample_fps) * 1000),
            )
            session.add(
                Frame(
                    video_id=video.id,
                    frame_number=index,
                    timestamp_ms=timestamp_ms,
                    storage_path=storage.persist(frame_path, "image/jpeg"),
                    width=metadata.width,
                    height=metadata.height,
                )
            )

        video.status = "READY_FOR_ANNOTATION"
        job.state = "READY_FOR_ANNOTATION"
        job.progress = 100
        job.completed_at = datetime.utcnow()
        job.lease_expires_at = None
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
        job.lease_expires_at = None
    if model_run:
        model_run.status = "RETRY_PENDING" if job and job.state == "RETRY_PENDING" else "FAILED"
        model_run.error_code = code
        model_run.error_message = message[-2000:]
    if job and job.state == "RETRY_PENDING":
        requeue_job_outbox(session, job)
    session.commit()


def _persist_frame_outputs(
    session: Session,
    model_run: ModelRun,
    frame: Frame,
    outputs: Sequence[PredictionOutput],
) -> List[ModelPrediction]:
    predictions = [
        ModelPrediction(
            model_run_id=model_run.id,
            frame_id=frame.id,
            label=output.label,
            confidence=output.confidence,
            annotation_type=output.annotation_type,
            geometry=output.geometry,
            track_id=(
                str(output.external_track_id) if output.external_track_id is not None else None
            ),
        )
        for output in outputs
    ]
    session.add_all(predictions)
    session.flush()

    if model_run.model_kind != "detection":
        return predictions
    person_indices = [index for index, output in enumerate(outputs) if output.label == "person"]
    board_indices = [index for index, output in enumerate(outputs) if output.label == "snowboard"]
    associations = associate_people_and_boards(
        [outputs[index].geometry for index in person_indices],
        [outputs[index].geometry for index in board_indices],
    )
    for association in associations:
        person = predictions[person_indices[association.person_index]]
        board = predictions[board_indices[association.board_index]]
        person.label = "rider"
        person.associated_prediction_id = board.id
        board.associated_prediction_id = person.id
        person.association_score = association.score
        board.association_score = association.score
        person.association_ambiguous = association.ambiguous
        board.association_ambiguous = association.ambiguous
    return predictions


def process_inference_job(
    session: Session,
    job_id: str,
    provider: Optional[PredictionProvider] = None,
    storage: Optional[LocalStorage] = None,
) -> None:
    storage = storage or create_storage()
    job = session.get(ProcessingJob, job_id)
    if job is None or job.model_run_id is None:
        raise ValueError("Inference job is missing its model run")
    model_run = session.get(ModelRun, job.model_run_id)
    if model_run is None:
        raise ValueError("Unknown model run {}".format(job.model_run_id))

    try:
        provider = provider or (
            OpenCVPIIProvider(settings.pii_screen_model)
            if model_run.model_kind == "pii"
            else UltralyticsProvider(model_run.model_name)
        )
        model_run.status = "RUNNING"
        model_run.started_at = datetime.utcnow()
        model_run.total_frames = len(model_run.video.frames)
        model_run.processed_frames = 0
        model_run.error_code = None
        model_run.error_message = None
        job.state = "RUNNING_INFERENCE"
        job.progress = 5
        renew_job_lease(job)
        session.execute(delete(ModelPrediction).where(ModelPrediction.model_run_id == model_run.id))
        session.commit()

        started_at = datetime.utcnow()
        threshold = float(model_run.parameters.get("confidence_threshold", 0.25))
        frames = list(model_run.video.frames)
        infer_frames = getattr(provider, "infer_frames", None)
        if callable(infer_frames):
            output_sequence = infer_frames(
                [storage.absolute_path(frame.storage_path) for frame in frames],
                model_run.model_kind,
                threshold,
                model_run.device,
            )
            if len(output_sequence) != len(frames):
                raise InferenceError(
                    "INVALID_INFERENCE_OUTPUT",
                    "Tracking provider returned {} frame results for {} frames".format(
                        len(output_sequence), len(frames)
                    ),
                )
            model_run.parameters = {
                **model_run.parameters,
                "tracking_enabled": True,
                "tracker": "ByteTrack+geometry-fallback-v1",
            }
        else:
            output_sequence = [
                provider.infer_frame(
                    storage.absolute_path(frame.storage_path),
                    model_run.model_kind,
                    threshold,
                    model_run.device,
                )
                for frame in frames
            ]

        persisted_predictions: List[ModelPrediction] = []
        for index, (frame, outputs) in enumerate(zip(frames, output_sequence), start=1):
            persisted_predictions.extend(
                _persist_frame_outputs(session, model_run, frame, outputs)
            )
            model_run.processed_frames = index
            job.progress = 5 + round((index / max(1, len(frames))) * 90)
            renew_job_lease(job)
            session.commit()

        rider_track_ids = {
            prediction.track_id
            for prediction in persisted_predictions
            if prediction.label == "rider" and prediction.track_id is not None
        }
        for prediction in persisted_predictions:
            if prediction.label == "person" and prediction.track_id in rider_track_ids:
                prediction.label = "rider"

        completed_at = datetime.utcnow()
        runtime_version = (
            provider.runtime_version
            if model_run.model_kind == "pii"
            else "ultralytics-{}".format(provider.runtime_version)
        )
        model_run.model_version = "{}+{}".format(model_run.model_version, runtime_version)
        model_run.latency_ms = round((completed_at - started_at).total_seconds() * 1000)
        model_run.status = "COMPLETED"
        model_run.completed_at = completed_at
        job.state = "COMPLETED"
        job.progress = 100
        job.completed_at = completed_at
        job.lease_expires_at = None
        route_model_run_reviews(session, model_run)
        session.commit()
    except InferenceError as error:
        record_inference_failure(session, job_id, error.code, str(error))
        logger.exception("Model inference failed", extra={"job_id": job_id})
    except Exception as error:
        record_inference_failure(session, job_id, "UNEXPECTED_INFERENCE_ERROR", str(error))
        logger.exception("Unexpected inference failure", extra={"job_id": job_id})


def record_sanitization_failure(
    session: Session,
    job_id: str,
    code: str,
    message: str,
    storage: Optional[LocalStorage] = None,
    residual_scan: Optional[dict] = None,
) -> None:
    session.rollback()
    job = session.get(ProcessingJob, job_id)
    item = session.get(SanitizedExport, job.sanitized_export_id) if job and job.sanitized_export_id else None
    if job:
        job.state = "FAILED"
        job.error_code = code
        job.error_message = message[-2000:]
        job.progress = 0
        job.lease_expires_at = None
    if item:
        item.status = "FAILED"
        item.error_code = code
        item.error_message = message[-2000:]
        if residual_scan:
            item.residual_scan_status = "FAILED"
            item.residual_findings = int(residual_scan.get("finding_count", 0))
            item.residual_model_version = residual_scan.get("model_version")
        storage = storage or create_storage()
        manifest_path = storage.sanitized_manifest_path(item.id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        failed_at = datetime.utcnow()
        item.processing_ms = round(
            (failed_at - ((job.started_at if job else None) or item.created_at)).total_seconds()
            * 1000
        )
        manifest = {
                    "schema_version": "1.0",
                    "status": "FAILED",
                    "export_id": item.id,
                    "video_id": item.video_id,
                    "task_id": item.task_id,
                    "reviewer": item.reviewer,
                    "error_code": code,
                    "error_message": message[-2000:],
                    "failed_at": failed_at.isoformat() + "Z",
                    "processing_ms": item.processing_ms,
                }
        if residual_scan:
            manifest["residual_pii_scan"] = residual_scan
        manifest_path.write_text(
            json.dumps(manifest, indent=2)
            + "\n",
            encoding="utf-8",
        )
        item.manifest_path = storage.persist(manifest_path, "application/json")
    session.commit()


def rectangle_union_area(rectangles) -> float:
    """Exact union area for axis-aligned intersections used by the residual gate."""
    if not rectangles:
        return 0.0
    x_edges = sorted({edge for rectangle in rectangles for edge in (rectangle[0], rectangle[2])})
    area = 0.0
    for left, right in zip(x_edges, x_edges[1:]):
        if right <= left:
            continue
        intervals = sorted(
            (top, bottom)
            for x1, top, x2, bottom in rectangles
            if x1 < right and x2 > left and bottom > top
        )
        covered_y = 0.0
        if intervals:
            current_top, current_bottom = intervals[0]
            for top, bottom in intervals[1:]:
                if top > current_bottom:
                    covered_y += current_bottom - current_top
                    current_top, current_bottom = top, bottom
                else:
                    current_bottom = max(current_bottom, bottom)
            covered_y += current_bottom - current_top
        area += (right - left) * covered_y
    return area


def scan_residual_pii(
    processor: FFmpegProcessor,
    provider: PredictionProvider,
    video_path,
    scan_directory,
    mask_segments,
    video_width: int,
    video_height: int,
    heartbeat=None,
) -> dict:
    """Fail-closed second-pass PII scan over the rendered artifact."""
    frames = processor.extract_frames(
        video_path, scan_directory, settings.residual_pii_scan_fps
    )
    if hasattr(provider, "infer_frame"):
        outputs_by_frame = []
        for frame_index, frame in enumerate(frames, start=1):
            outputs_by_frame.append(
                provider.infer_frame(
                    frame,
                    "pii",
                    settings.residual_pii_confidence,
                    settings.residual_pii_device,
                )
            )
            if heartbeat and (frame_index % 10 == 0 or frame_index == len(frames)):
                heartbeat()
    else:
        outputs_by_frame = provider.infer_frames(
            frames,
            "pii",
            settings.residual_pii_confidence,
            settings.residual_pii_device,
        )
        if heartbeat:
            heartbeat()
    findings = []
    covered_redetections = []
    for frame_index, outputs in enumerate(outputs_by_frame, start=1):
        timestamp_seconds = (frame_index - 1) / settings.residual_pii_scan_fps
        for output in outputs:
            if output.label not in {"face", "license_plate", "screen"}:
                continue
            geometry = output.geometry
            detection = {
                "frame_number": frame_index,
                "timestamp_ms": round(timestamp_seconds * 1000),
                "label": output.label,
                "confidence": output.confidence,
                "geometry": geometry,
                "track_id": (
                    str(output.external_track_id)
                    if output.external_track_id is not None
                    else None
                ),
            }
            x1 = float(geometry["x"]) * video_width
            y1 = float(geometry["y"]) * video_height
            x2 = x1 + float(geometry["width"]) * video_width
            y2 = y1 + float(geometry["height"]) * video_height
            detection_area = max(1.0, (x2 - x1) * (y2 - y1))
            intersections = []
            for segment in mask_segments:
                if not segment.start_seconds <= timestamp_seconds <= segment.end_seconds:
                    continue
                for rectangle in segment.rectangles:
                    intersection = (
                        max(x1, rectangle.x),
                        max(y1, rectangle.y),
                        min(x2, rectangle.x + rectangle.width),
                        min(y2, rectangle.y + rectangle.height),
                    )
                    if intersection[2] > intersection[0] and intersection[3] > intersection[1]:
                        intersections.append(intersection)
            covered_area = rectangle_union_area(intersections)
            detection["mask_coverage"] = min(1.0, covered_area / detection_area)
            if detection["mask_coverage"] >= settings.residual_pii_mask_coverage:
                covered_redetections.append(detection)
            else:
                findings.append(detection)
    for frame in frames:
        frame.unlink(missing_ok=True)
    if scan_directory.exists():
        scan_directory.rmdir()
    return {
        "status": "PASSED" if not findings else "FAILED",
        "model_version": provider.runtime_version,
        "provider": getattr(provider, "provider_name", provider.__class__.__name__),
        "model_name": getattr(provider, "model_name", None),
        "model_revision": getattr(provider, "model_revision", None),
        "sample_fps": settings.residual_pii_scan_fps,
        "confidence_threshold": settings.residual_pii_confidence,
        "mask_coverage_threshold": settings.residual_pii_mask_coverage,
        "scanned_frames": len(frames),
        "finding_count": len(findings),
        "findings": findings,
        "covered_redetection_count": len(covered_redetections),
        "covered_redetections": covered_redetections,
    }


def process_sanitization_job(
    session: Session,
    job_id: str,
    processor: Optional[FFmpegProcessor] = None,
    storage: Optional[LocalStorage] = None,
    residual_provider: Optional[PredictionProvider] = None,
) -> None:
    processor = processor or FFmpegProcessor()
    storage = storage or create_storage()
    job = session.get(ProcessingJob, job_id)
    if job is None or job.sanitized_export_id is None:
        raise ValueError("Sanitization job is missing its export")
    item = session.get(SanitizedExport, job.sanitized_export_id)
    if item is None:
        raise ValueError("Unknown sanitized export")
    try:
        item.status = "RUNNING"
        job.state = "SANITIZING_VIDEO"
        job.progress = 10
        renew_job_lease(job)
        session.commit()
        annotations = list(
            session.scalars(
                select(Annotation).where(
                    Annotation.task_id == item.task_id,
                    Annotation.annotation_type.in_(("bbox", "mask")),
                    Annotation.label.in_(item.labels),
                )
            ).all()
        )
        if not annotations:
            raise MediaProcessingError("NO_PII_REGIONS", "No PII annotations remain for export")
        if not item.video.width or not item.video.height:
            raise MediaProcessingError("MISSING_VIDEO_DIMENSIONS", "Video dimensions are unavailable")
        segments = build_mask_segments(item.video, annotations)
        filter_graph, output_label = build_ffmpeg_mask_filter(
            item.video.width,
            item.video.height,
            segments,
            (item.video.duration_ms or 0) / 1000,
        )
        destination = storage.sanitized_video_path(item.id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [
            settings.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(storage.absolute_path(item.video.storage_path)),
            "-filter_complex",
            filter_graph,
            "-map",
            output_label,
            "-map",
            "0:a?",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(destination),
        ]
        processor._run(command, "SANITIZATION_FAILED")
        job.progress = 90
        if settings.residual_pii_scan_enabled:
            scan_directory = destination.parent / "residual-scan"
            try:
                residual_provider = residual_provider or create_residual_pii_provider()

                def scan_heartbeat():
                    renew_job_lease(job)
                    session.commit()

                residual_scan = scan_residual_pii(
                    processor,
                    residual_provider,
                    destination,
                    scan_directory,
                    segments,
                    item.video.width,
                    item.video.height,
                    heartbeat=scan_heartbeat,
                )
            except Exception as error:
                for scan_file in (
                    scan_directory.glob("*") if scan_directory.exists() else []
                ):
                    scan_file.unlink(missing_ok=True)
                if scan_directory.exists():
                    scan_directory.rmdir()
                destination.unlink(missing_ok=True)
                record_sanitization_failure(
                    session,
                    job_id,
                    "RESIDUAL_SCAN_FAILED",
                    str(error),
                    storage,
                    {
                        "status": "FAILED",
                        "finding_count": 0,
                        "provider": settings.residual_pii_provider,
                        "model_name": settings.residual_pii_model,
                        "model_revision": settings.residual_pii_model_revision,
                        "model_version": "{}@{}".format(
                            settings.residual_pii_model,
                            settings.residual_pii_model_revision,
                        ),
                        "sample_fps": settings.residual_pii_scan_fps,
                        "confidence_threshold": settings.residual_pii_confidence,
                        "error": str(error)[-2000:],
                    },
                )
                return
            item.residual_scan_status = residual_scan["status"]
            item.residual_findings = residual_scan["finding_count"]
            item.residual_model_version = residual_scan["model_version"]
            if residual_scan["finding_count"]:
                destination.unlink(missing_ok=True)
                record_sanitization_failure(
                    session,
                    job_id,
                    "RESIDUAL_PII_DETECTED",
                    "Residual scan found {} possible PII regions".format(
                        residual_scan["finding_count"]
                    ),
                    storage,
                    residual_scan,
                )
                return
        else:
            residual_scan = {
                "status": "SKIPPED",
                "finding_count": 0,
                "reason": "MEDIA_RESIDUAL_PII_SCAN is disabled",
            }
            item.residual_scan_status = "SKIPPED"
        output_sha256 = sha256_file(destination)
        manifest_path = storage.sanitized_manifest_path(item.id)
        completed_at = datetime.utcnow()
        processing_ms = round(
            (completed_at - (job.started_at or item.created_at)).total_seconds() * 1000
        )
        source_predictions = [
            session.get(ModelPrediction, annotation.model_prediction_id)
            for annotation in annotations
            if annotation.model_prediction_id
        ]
        source_predictions = [prediction for prediction in source_predictions if prediction]
        models = {
            prediction.model_run.id: {
                "run_id": prediction.model_run.id,
                "provider": prediction.model_run.provider,
                "model_name": prediction.model_run.model_name,
                "model_version": prediction.model_run.model_version,
                "parameters": prediction.model_run.parameters,
            }
            for prediction in source_predictions
        }
        tracks = sorted(
            {
                prediction.track_id
                for prediction in source_predictions
                if prediction.track_id is not None
            }
        )
        manifest = {
            "schema_version": "1.0",
            "status": "COMPLETED",
            "export_id": item.id,
            "video_id": item.video_id,
            "task_id": item.task_id,
            "source_sha256": sha256_file(storage.absolute_path(item.video.storage_path)),
            "output_sha256": output_sha256,
            "labels": item.labels,
            "reviewer": item.reviewer,
            "models": list(models.values()),
            "blurred_track_ids": tracks,
            "source_annotation_count": len(annotations),
            "segments": [mask_segment_manifest(segment) for segment in segments],
            "residual_pii_scan": residual_scan,
            "started_at": (job.started_at or item.created_at).isoformat() + "Z",
            "completed_at": completed_at.isoformat() + "Z",
            "processing_ms": processing_ms,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        item.storage_path = storage.persist(destination, "video/mp4")
        item.manifest_path = storage.persist(manifest_path, "application/json")
        item.output_sha256 = output_sha256
        item.source_annotation_count = len(annotations)
        item.processing_ms = processing_ms
        item.status = "COMPLETED"
        item.completed_at = completed_at
        job.state = "COMPLETED"
        job.progress = 100
        job.completed_at = completed_at
        job.lease_expires_at = None
        session.commit()
    except MediaProcessingError as error:
        record_sanitization_failure(session, job_id, error.code, str(error), storage)
    except Exception as error:
        record_sanitization_failure(
            session, job_id, "UNEXPECTED_SANITIZATION_ERROR", str(error), storage
        )
