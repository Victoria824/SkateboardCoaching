import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .api.inference import router as inference_router
from .api.quality import router as quality_router
from .config import settings
from .database import get_session
from .models import (
    Annotation,
    AnnotationActivity,
    AnnotationTask,
    Frame,
    ModelPrediction,
    PredictionDecision,
    ProcessingJob,
    Video,
)
from .schemas import (
    AnnotationResponse,
    AnnotationSaveRequest,
    AnnotationSaveResponse,
    AnnotationTaskDetail,
    AnnotationTaskResponse,
    FrameResponse,
    JobResponse,
    UploadResponse,
    VideoResponse,
)
from .storage import LocalStorage, UploadTooLarge, safe_filename


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
storage = LocalStorage()


app = FastAPI(
    title="Snowboard Vision Media Service",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)
app.mount(settings.public_media_url, StaticFiles(directory=str(settings.media_root)), name="media")
app.include_router(inference_router)
app.include_router(quality_router)


ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
SAMPLING_PROFILES = {"overview": 1.0, "action": 5.0}


def frame_response(frame: Frame) -> FrameResponse:
    return FrameResponse(
        id=frame.id,
        video_id=frame.video_id,
        frame_number=frame.frame_number,
        timestamp_ms=frame.timestamp_ms,
        image_url="{}/{}".format(settings.public_media_url, frame.storage_path),
        width=frame.width,
        height=frame.height,
    )


def video_response(video: Video, include_frames: bool = True) -> VideoResponse:
    return VideoResponse(
        id=video.id,
        filename=video.filename,
        mime_type=video.mime_type,
        file_size=video.file_size,
        duration_ms=video.duration_ms,
        fps=video.fps,
        width=video.width,
        height=video.height,
        codec=video.codec,
        source_frame_count=video.source_frame_count,
        sampling_profile=video.sampling_profile,
        sample_fps=video.sample_fps,
        status=video.status,
        created_at=video.created_at,
        frames=[frame_response(frame) for frame in video.frames] if include_frames else [],
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "media"}


@app.post("/api/videos", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_video(
    response: Response,
    video_file: UploadFile = File(..., alias="video"),
    sampling_profile: str = Form("overview"),
    sample_fps: Optional[float] = Form(None),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> UploadResponse:
    normalized_profile = sampling_profile.strip().lower()
    if normalized_profile in SAMPLING_PROFILES:
        resolved_sample_fps = SAMPLING_PROFILES[normalized_profile]
    elif normalized_profile == "custom" and sample_fps is not None and 0.1 <= sample_fps <= 30:
        resolved_sample_fps = sample_fps
    else:
        raise HTTPException(
            status_code=422,
            detail="Sampling profile must be overview, action, or custom with sample_fps from 0.1 to 30",
        )
    if idempotency_key:
        existing = session.scalar(
            select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
        )
        if existing:
            response.headers["Location"] = "/api/jobs/{}".format(existing.id)
            return UploadResponse(video=video_response(existing.video, False), job=JobResponse.model_validate(existing))

    filename = safe_filename(video_file.filename or "video")
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported video extension")
    if video_file.content_type and not video_file.content_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="Uploaded file must be a video")

    video = Video(
        filename=filename,
        storage_path="pending",
        mime_type=video_file.content_type,
        file_size=0,
        sampling_profile=normalized_profile,
        sample_fps=resolved_sample_fps,
    )
    session.add(video)
    session.flush()
    destination = storage.video_path(video.id, filename)
    try:
        size = storage.write_stream(destination, video_file.file, settings.max_upload_bytes)
    except UploadTooLarge as error:
        session.rollback()
        raise HTTPException(status_code=413, detail=str(error))
    finally:
        video_file.file.close()

    video.storage_path = storage.relative_path(destination)
    video.file_size = size
    video.status = "QUEUED"
    job = ProcessingJob(
        video=video,
        job_type="VIDEO_INGESTION",
        state="QUEUED",
        progress=0,
        idempotency_key=idempotency_key,
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Idempotency key is already in use")
    session.refresh(video)
    session.refresh(job)
    response.headers["Location"] = "/api/jobs/{}".format(job.id)
    return UploadResponse(video=video_response(video, False), job=JobResponse.model_validate(job))


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, session: Session = Depends(get_session)) -> JobResponse:
    job = session.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@app.post("/api/jobs/{job_id}/retry", response_model=JobResponse, status_code=202)
def retry_job(job_id: str, session: Session = Depends(get_session)) -> JobResponse:
    job = session.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.state not in {"FAILED", "RETRY_PENDING"}:
        raise HTTPException(status_code=409, detail="Only failed jobs can be retried")
    if job.attempts >= job.max_attempts:
        job.attempts = 0
    job.state = "QUEUED"
    job.error_code = None
    job.error_message = None
    session.commit()
    return JobResponse.model_validate(job)


@app.get("/api/videos/{video_id}", response_model=VideoResponse)
def get_video(video_id: str, session: Session = Depends(get_session)) -> VideoResponse:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video_response(video)


@app.get("/api/videos/{video_id}/frames", response_model=List[FrameResponse])
def list_frames(video_id: str, session: Session = Depends(get_session)) -> List[FrameResponse]:
    if session.get(Video, video_id) is None:
        raise HTTPException(status_code=404, detail="Video not found")
    frames = session.scalars(
        select(Frame).where(Frame.video_id == video_id).order_by(Frame.frame_number)
    ).all()
    return [frame_response(frame) for frame in frames]


@app.post("/api/videos/{video_id}/annotation-tasks", response_model=AnnotationTaskResponse, status_code=201)
def create_annotation_task(
    video_id: str,
    assigned_to: Optional[str] = None,
    force_new: bool = False,
    session: Session = Depends(get_session),
) -> AnnotationTaskResponse:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status != "READY_FOR_ANNOTATION":
        raise HTTPException(status_code=409, detail="Video is not ready for annotation")
    if not force_new:
        existing = session.scalar(
            select(AnnotationTask)
            .where(AnnotationTask.video_id == video_id, AnnotationTask.status != "COMPLETED")
            .order_by(AnnotationTask.created_at)
            .limit(1)
        )
        if existing:
            return AnnotationTaskResponse.model_validate(existing)
    task = AnnotationTask(video=video, status="PENDING", assigned_to=assigned_to)
    session.add(task)
    session.commit()
    session.refresh(task)
    return AnnotationTaskResponse.model_validate(task)

@app.get("/api/annotation-tasks/{task_id}", response_model=AnnotationTaskDetail)
def get_annotation_task(task_id: str, session: Session = Depends(get_session)) -> AnnotationTaskDetail:
    task = session.get(AnnotationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Annotation task not found")
    return AnnotationTaskDetail(
        **AnnotationTaskResponse.model_validate(task).model_dump(),
        video=video_response(task.video),
    )


def require_task_frame(session: Session, task_id: str, frame_id: str):
    task = session.get(AnnotationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Annotation task not found")
    frame = session.get(Frame, frame_id)
    if frame is None or frame.video_id != task.video_id:
        raise HTTPException(status_code=404, detail="Frame does not belong to this task")
    return task, frame


@app.get(
    "/api/annotation-tasks/{task_id}/frames/{frame_id}/annotations",
    response_model=List[AnnotationResponse],
)
def list_annotations(task_id: str, frame_id: str, session: Session = Depends(get_session)):
    require_task_frame(session, task_id, frame_id)
    return session.scalars(
        select(Annotation)
        .where(Annotation.task_id == task_id, Annotation.frame_id == frame_id)
        .order_by(Annotation.created_at)
    ).all()


@app.put(
    "/api/annotation-tasks/{task_id}/frames/{frame_id}/annotations",
    response_model=AnnotationSaveResponse,
)
def save_annotations(
    task_id: str,
    frame_id: str,
    request: AnnotationSaveRequest,
    session: Session = Depends(get_session),
) -> AnnotationSaveResponse:
    task, _ = require_task_frame(session, task_id, frame_id)
    session.execute(
        delete(Annotation).where(Annotation.task_id == task_id, Annotation.frame_id == frame_id)
    )
    saved = [
        Annotation(task_id=task_id, frame_id=frame_id, **item.model_dump())
        for item in request.annotations
    ]
    session.add_all(saved)
    session.flush()
    for annotation in saved:
        if not annotation.model_prediction_id:
            continue
        prediction = session.get(ModelPrediction, annotation.model_prediction_id)
        if prediction is None or prediction.frame_id != frame_id:
            session.rollback()
            raise HTTPException(status_code=422, detail="Invalid model prediction reference")
        if prediction.status != "PENDING":
            continue
        action = "CORRECTED" if annotation.source == "model_corrected" else "ACCEPTED"
        prediction.status = action
        prediction.resolved_at = datetime.utcnow()
        session.add(
            PredictionDecision(
                prediction_id=prediction.id,
                task_id=task_id,
                annotation_id=annotation.id,
                action=action,
                duration_ms=request.duration_ms,
            )
        )
    session.add(
        AnnotationActivity(
            task_id=task_id,
            frame_id=frame_id,
            action="SAVE",
            duration_ms=request.duration_ms,
            annotation_count=len(saved),
        )
    )
    if task.status == "PENDING":
        task.status = "IN_PROGRESS"
    session.commit()
    for annotation in saved:
        session.refresh(annotation)
    return AnnotationSaveResponse(annotations=saved, saved_count=len(saved))


@app.post("/api/annotation-tasks/{task_id}/complete", response_model=AnnotationTaskResponse)
def complete_annotation_task(task_id: str, session: Session = Depends(get_session)):
    task = session.get(AnnotationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Annotation task not found")
    task.status = "COMPLETED"
    task.completed_at = datetime.utcnow()
    session.commit()
    return AnnotationTaskResponse.model_validate(task)
