import logging
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .database import create_schema, get_session
from .models import (
    Annotation,
    AnnotationActivity,
    AnnotationTask,
    Frame,
    ModelPrediction,
    ModelRun,
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
    ModelMetricsResponse,
    ModelPredictionResponse,
    ModelRunCreatedResponse,
    ModelRunRequest,
    ModelRunResponse,
    PredictionDecisionResponse,
    PredictionRejectRequest,
    UploadResponse,
    VideoResponse,
)
from .storage import LocalStorage, UploadTooLarge, safe_filename


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
storage = LocalStorage()


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    yield


app = FastAPI(
    title="Snowboard Vision Media Service",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.mount(settings.public_media_url, StaticFiles(directory=str(settings.media_root)), name="media")


ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}


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
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> UploadResponse:
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

    video = Video(filename=filename, storage_path="pending", mime_type=video_file.content_type, file_size=0)
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
def create_annotation_task(video_id: str, session: Session = Depends(get_session)) -> AnnotationTaskResponse:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status != "READY_FOR_ANNOTATION":
        raise HTTPException(status_code=409, detail="Video is not ready for annotation")
    existing = session.scalar(
        select(AnnotationTask)
        .where(AnnotationTask.video_id == video_id, AnnotationTask.status != "COMPLETED")
        .order_by(AnnotationTask.created_at)
        .limit(1)
    )
    if existing:
        return AnnotationTaskResponse.model_validate(existing)
    task = AnnotationTask(video=video, status="PENDING")
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


def prediction_response(prediction: ModelPrediction) -> ModelPredictionResponse:
    return ModelPredictionResponse(
        id=prediction.id,
        model_run_id=prediction.model_run_id,
        frame_id=prediction.frame_id,
        label=prediction.label,
        confidence=prediction.confidence,
        annotation_type=prediction.annotation_type,
        geometry=prediction.geometry,
        status=prediction.status,
        model_name=prediction.model_run.model_name,
        model_version=prediction.model_run.model_version,
        created_at=prediction.created_at,
        resolved_at=prediction.resolved_at,
    )


@app.post("/api/videos/{video_id}/model-runs", response_model=ModelRunCreatedResponse, status_code=202)
def create_model_run(
    video_id: str,
    request: ModelRunRequest,
    session: Session = Depends(get_session),
) -> ModelRunCreatedResponse:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status != "READY_FOR_ANNOTATION" or not video.frames:
        raise HTTPException(status_code=409, detail="Video frames are not ready for inference")
    default_model = "yolo11n-pose.pt" if request.model_kind == "pose" else "yolo11n.pt"
    model_run = ModelRun(
        video=video,
        model_kind=request.model_kind,
        provider=request.provider,
        model_name=request.model_name or default_model,
        model_version=request.model_version,
        device=request.device,
        parameters={"confidence_threshold": request.confidence_threshold},
        status="QUEUED",
        total_frames=len(video.frames),
    )
    job = ProcessingJob(
        video=video,
        model_run=model_run,
        job_type="MODEL_INFERENCE",
        state="QUEUED",
        progress=0,
    )
    session.add_all([model_run, job])
    session.commit()
    session.refresh(model_run)
    session.refresh(job)
    return ModelRunCreatedResponse(
        model_run=ModelRunResponse.model_validate(model_run),
        job=JobResponse.model_validate(job),
    )


@app.get("/api/model-runs/{model_run_id}", response_model=ModelRunResponse)
def get_model_run(model_run_id: str, session: Session = Depends(get_session)):
    model_run = session.get(ModelRun, model_run_id)
    if model_run is None:
        raise HTTPException(status_code=404, detail="Model run not found")
    return ModelRunResponse.model_validate(model_run)


@app.get("/api/frames/{frame_id}/predictions", response_model=List[ModelPredictionResponse])
def list_predictions(frame_id: str, session: Session = Depends(get_session)):
    if session.get(Frame, frame_id) is None:
        raise HTTPException(status_code=404, detail="Frame not found")
    predictions = session.scalars(
        select(ModelPrediction)
        .where(ModelPrediction.frame_id == frame_id)
        .order_by(ModelPrediction.created_at)
    ).all()
    return [prediction_response(prediction) for prediction in predictions]


@app.post(
    "/api/predictions/{prediction_id}/reject",
    response_model=PredictionDecisionResponse,
)
def reject_prediction(
    prediction_id: str,
    request: PredictionRejectRequest,
    session: Session = Depends(get_session),
) -> PredictionDecisionResponse:
    prediction = session.get(ModelPrediction, prediction_id)
    task = session.get(AnnotationTask, request.task_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if task is None or prediction.model_run.video_id != task.video_id:
        raise HTTPException(status_code=404, detail="Prediction does not belong to this task")
    if prediction.status != "PENDING":
        raise HTTPException(status_code=409, detail="Prediction has already been resolved")
    prediction.status = "REJECTED"
    prediction.resolved_at = datetime.utcnow()
    session.add(
        PredictionDecision(
            prediction_id=prediction.id,
            task_id=task.id,
            action="REJECTED",
            duration_ms=request.duration_ms,
        )
    )
    session.commit()
    return PredictionDecisionResponse(prediction_id=prediction.id, status=prediction.status)


@app.get("/api/model-runs/{model_run_id}/metrics", response_model=ModelMetricsResponse)
def get_model_metrics(model_run_id: str, session: Session = Depends(get_session)):
    if session.get(ModelRun, model_run_id) is None:
        raise HTTPException(status_code=404, detail="Model run not found")
    predictions = session.scalars(
        select(ModelPrediction).where(ModelPrediction.model_run_id == model_run_id)
    ).all()
    counts = {state: 0 for state in ("PENDING", "ACCEPTED", "CORRECTED", "REJECTED")}
    by_label = {}
    for prediction in predictions:
        counts[prediction.status] = counts.get(prediction.status, 0) + 1
        label_counts = by_label.setdefault(
            prediction.label,
            {state.lower(): 0 for state in ("PENDING", "ACCEPTED", "CORRECTED", "REJECTED")},
        )
        label_counts[prediction.status.lower()] += 1
    decided = counts["ACCEPTED"] + counts["CORRECTED"] + counts["REJECTED"]
    average_duration = session.scalar(
        select(func.avg(PredictionDecision.duration_ms))
        .join(ModelPrediction)
        .where(
            ModelPrediction.model_run_id == model_run_id,
            PredictionDecision.duration_ms.is_not(None),
        )
    )
    return ModelMetricsResponse(
        model_run_id=model_run_id,
        total_predictions=len(predictions),
        pending=counts["PENDING"],
        accepted=counts["ACCEPTED"],
        corrected=counts["CORRECTED"],
        rejected=counts["REJECTED"],
        acceptance_rate=(counts["ACCEPTED"] / decided) if decided else 0,
        correction_rate=(counts["CORRECTED"] / decided) if decided else 0,
        rejection_rate=(counts["REJECTED"] / decided) if decided else 0,
        average_decision_time_ms=float(average_duration) if average_duration is not None else None,
        by_label=by_label,
    )
