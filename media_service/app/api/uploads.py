from datetime import datetime, timedelta
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_session
from ..models import DirectUpload, ProcessingJob, Video
from ..schemas import (
    DirectUploadRequest,
    DirectUploadResponse,
    JobResponse,
    UploadResponse,
    VideoResponse,
)
from ..storage import S3ObjectStore, safe_filename


router = APIRouter(prefix="/api", tags=["direct uploads"])
SAMPLING_PROFILES = {"overview": 1.0, "action": 5.0, "motion": 5.0}
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}


def get_object_store():
    return S3ObjectStore()


def _require_s3():
    if settings.storage_backend != "s3":
        raise HTTPException(
            status_code=409,
            detail="Direct signed uploads require MEDIA_STORAGE_BACKEND=s3",
        )


@router.post(
    "/direct-uploads",
    response_model=DirectUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def initiate_direct_upload(
    request: DirectUploadRequest,
    session: Session = Depends(get_session),
):
    _require_s3()
    if request.size_bytes > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Upload exceeds configured maximum")
    if Path(request.filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported video extension")
    sample_fps = (
        request.sample_fps
        if request.sampling_profile == "custom"
        else SAMPLING_PROFILES[request.sampling_profile]
    )
    if sample_fps is None:
        raise HTTPException(status_code=422, detail="Custom sampling requires sample_fps")
    upload_id = str(uuid.uuid4())
    object_key = "videos/{}/{}".format(upload_id, safe_filename(request.filename))
    expires_at = datetime.utcnow() + timedelta(seconds=settings.s3_presign_ttl_seconds)
    item = DirectUpload(
        id=upload_id,
        object_key=object_key,
        filename=safe_filename(request.filename),
        content_type=request.content_type,
        expected_size=request.size_bytes,
        expected_sha256=request.sha256,
        sampling_profile=request.sampling_profile,
        sample_fps=sample_fps,
        expires_at=expires_at,
    )
    session.add(item)
    session.commit()
    return DirectUploadResponse(
        upload_id=item.id,
        object_key=item.object_key,
        upload_url=get_object_store().presign_put(
            item.object_key, item.content_type, item.expected_sha256
        ),
        required_headers={
            "Content-Type": item.content_type,
            "x-amz-meta-sha256": item.expected_sha256,
        },
        expires_at=item.expires_at,
    )


@router.post(
    "/direct-uploads/{upload_id}/complete",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def complete_direct_upload(upload_id: str, session: Session = Depends(get_session)):
    _require_s3()
    item = session.get(DirectUpload, upload_id, with_for_update=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Direct upload not found")
    if item.status == "COMPLETED" and item.video:
        job = next(job for job in item.video.jobs if job.job_type == "VIDEO_INGESTION")
        return UploadResponse(
            video=VideoResponse(
                id=item.video.id,
                filename=item.video.filename,
                mime_type=item.video.mime_type,
                file_size=item.video.file_size,
                duration_ms=item.video.duration_ms,
                fps=item.video.fps,
                width=item.video.width,
                height=item.video.height,
                codec=item.video.codec,
                source_frame_count=item.video.source_frame_count,
                sampling_profile=item.video.sampling_profile,
                sample_fps=item.video.sample_fps,
                status=item.video.status,
                created_at=item.video.created_at,
            ),
            job=JobResponse.model_validate(job),
        )
    if item.expires_at < datetime.utcnow():
        item.status = "EXPIRED"
        session.commit()
        raise HTTPException(status_code=410, detail="Direct upload has expired")
    try:
        metadata = get_object_store().head(item.object_key)
    except Exception as error:
        raise HTTPException(status_code=409, detail="Uploaded object is unavailable") from error
    if int(metadata.get("ContentLength", -1)) != item.expected_size:
        raise HTTPException(status_code=409, detail="Uploaded object size does not match")
    uploaded_sha256 = (metadata.get("Metadata") or {}).get("sha256")
    if uploaded_sha256 != item.expected_sha256:
        raise HTTPException(status_code=409, detail="Uploaded object checksum metadata does not match")
    video = Video(
        filename=item.filename,
        storage_path=item.object_key,
        mime_type=item.content_type,
        file_size=item.expected_size,
        source_sha256=item.expected_sha256,
        sampling_profile=item.sampling_profile,
        sample_fps=item.sample_fps,
        status="QUEUED",
    )
    job = ProcessingJob(video=video, job_type="VIDEO_INGESTION", state="QUEUED")
    item.status = "COMPLETED"
    item.video = video
    item.completed_at = datetime.utcnow()
    session.add_all([video, job])
    session.commit()
    return UploadResponse(
        video=VideoResponse(
            id=video.id,
            filename=video.filename,
            mime_type=video.mime_type,
            file_size=video.file_size,
            duration_ms=None,
            fps=None,
            width=None,
            height=None,
            codec=None,
            source_frame_count=None,
            sampling_profile=video.sampling_profile,
            sample_fps=video.sample_fps,
            status=video.status,
            created_at=video.created_at,
        ),
        job=JobResponse.model_validate(job),
    )
