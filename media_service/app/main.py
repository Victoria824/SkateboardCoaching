import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .database import create_schema, get_session
from .models import Frame, ProcessingJob, Video
from .schemas import FrameResponse, JobResponse, UploadResponse, VideoResponse
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
    job = ProcessingJob(video=video, state="QUEUED", progress=0, idempotency_key=idempotency_key)
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

