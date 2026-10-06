from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_session
from ..models import Annotation, AnnotationTask, ProcessingJob, SanitizedExport, Video
from ..privacy import PII_LABELS
from ..schemas import (
    JobResponse,
    SanitizedExportCreatedResponse,
    SanitizedExportRequest,
    SanitizedExportResponse,
)


router = APIRouter(prefix="/api", tags=["privacy exports"])


def export_response(item: SanitizedExport) -> SanitizedExportResponse:
    return SanitizedExportResponse(
        id=item.id,
        video_id=item.video_id,
        task_id=item.task_id,
        status=item.status,
        labels=item.labels,
        source_annotation_count=item.source_annotation_count,
        video_url=(
            "{}/{}".format(settings.public_media_url, item.storage_path)
            if item.storage_path
            else None
        ),
        manifest_url=(
            "{}/{}".format(settings.public_media_url, item.manifest_path)
            if item.manifest_path
            else None
        ),
        output_sha256=item.output_sha256,
        error_code=item.error_code,
        error_message=item.error_message,
        created_at=item.created_at,
        completed_at=item.completed_at,
    )


@router.post(
    "/videos/{video_id}/sanitized-exports",
    response_model=SanitizedExportCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_sanitized_export(
    video_id: str,
    request: SanitizedExportRequest,
    session: Session = Depends(get_session),
):
    video = session.get(Video, video_id)
    task = session.get(AnnotationTask, request.task_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if task is None or task.video_id != video.id:
        raise HTTPException(status_code=404, detail="Annotation task does not belong to video")
    labels = sorted(set(request.labels))
    if not labels or not set(labels).issubset(PII_LABELS):
        raise HTTPException(status_code=422, detail="At least one supported PII label is required")
    annotation_count = len(
        session.scalars(
            select(Annotation).where(
                Annotation.task_id == task.id,
                Annotation.annotation_type == "bbox",
                Annotation.label.in_(labels),
            )
        ).all()
    )
    if annotation_count == 0:
        raise HTTPException(status_code=409, detail="Task has no matching PII annotations")
    sanitized_export = SanitizedExport(
        video=video,
        task=task,
        status="QUEUED",
        labels=labels,
        source_annotation_count=annotation_count,
    )
    job = ProcessingJob(
        video=video,
        sanitized_export=sanitized_export,
        job_type="PII_SANITIZATION",
        state="QUEUED",
    )
    session.add_all([sanitized_export, job])
    session.commit()
    return SanitizedExportCreatedResponse(
        sanitized_export=export_response(sanitized_export),
        job=JobResponse.model_validate(job),
    )


@router.get("/sanitized-exports/{export_id}", response_model=SanitizedExportResponse)
def get_sanitized_export(export_id: str, session: Session = Depends(get_session)):
    item = session.get(SanitizedExport, export_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Sanitized export not found")
    return export_response(item)


@router.get("/videos/{video_id}/sanitized-exports", response_model=List[SanitizedExportResponse])
def list_sanitized_exports(video_id: str, session: Session = Depends(get_session)):
    if session.get(Video, video_id) is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return [
        export_response(item)
        for item in session.scalars(
            select(SanitizedExport)
            .where(SanitizedExport.video_id == video_id)
            .order_by(SanitizedExport.created_at.desc())
        ).all()
    ]
