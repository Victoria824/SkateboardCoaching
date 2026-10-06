from collections import Counter
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_session
from ..models import (
    Annotation,
    AnnotationActivity,
    AnnotationPropagation,
    AnnotationTask,
    Frame,
    ModelPrediction,
    ModelRun,
    ReviewEvent,
    ReviewItem,
    Video,
)
from ..quality import annotation_agreement, route_model_run_reviews
from ..schemas import (
    AgreementResponse,
    DatasetHealthResponse,
    ReviewItemResponse,
    ReviewResolveRequest,
)


router = APIRouter(prefix="/api", tags=["quality and review"])


def _review_response(session: Session, item: ReviewItem) -> ReviewItemResponse:
    task = session.scalar(
        select(AnnotationTask)
        .where(AnnotationTask.video_id == item.video_id, AnnotationTask.status != "COMPLETED")
        .order_by(AnnotationTask.created_at.desc())
        .limit(1)
    )
    if task is None:
        task = session.scalar(
            select(AnnotationTask)
            .where(AnnotationTask.video_id == item.video_id)
            .order_by(AnnotationTask.created_at.desc())
            .limit(1)
        )
    return ReviewItemResponse(
        id=item.id,
        video_id=item.video_id,
        frame_id=item.frame_id,
        model_run_id=item.model_run_id,
        prediction_id=item.prediction_id,
        reason=item.reason,
        severity=item.severity,
        status=item.status,
        score=item.score,
        details=item.details,
        frame_number=item.frame.frame_number,
        timestamp_ms=item.frame.timestamp_ms,
        image_url="{}/{}".format(settings.public_media_url, item.frame.storage_path),
        prediction_label=item.prediction.label if item.prediction else None,
        prediction_confidence=item.prediction.confidence if item.prediction else None,
        prediction_track_id=item.prediction.track_id if item.prediction else None,
        association_score=item.prediction.association_score if item.prediction else None,
        annotation_task_id=task.id if task else None,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
    )


@router.get("/review-items", response_model=List[ReviewItemResponse])
def list_review_items(
    status: Optional[str] = Query(default="OPEN"),
    video_id: Optional[str] = None,
    session: Session = Depends(get_session),
):
    query = select(ReviewItem).order_by(ReviewItem.created_at.desc())
    if status:
        query = query.where(ReviewItem.status == status.upper())
    if video_id:
        query = query.where(ReviewItem.video_id == video_id)
    return [_review_response(session, item) for item in session.scalars(query).all()]


@router.post("/review-items/{review_item_id}/resolve", response_model=ReviewItemResponse)
def resolve_review_item(
    review_item_id: str,
    request: ReviewResolveRequest,
    session: Session = Depends(get_session),
):
    item = session.get(ReviewItem, review_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    if item.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="Review item has already been resolved")
    if request.action == "ESCALATED":
        item.status = "ESCALATED"
    elif request.action == "NEEDS_CORRECTION":
        item.status = "NEEDS_CORRECTION"
    else:
        item.status = "RESOLVED"
    item.resolved_at = datetime.utcnow() if item.status == "RESOLVED" else None
    session.add(
        ReviewEvent(
            review_item=item,
            action=request.action,
            reviewer=request.reviewer,
            note=request.note,
        )
    )
    session.commit()
    session.refresh(item)
    return _review_response(session, item)


@router.post("/videos/{video_id}/review-items/route", response_model=List[ReviewItemResponse])
def route_video_reviews(video_id: str, session: Session = Depends(get_session)):
    if session.get(Video, video_id) is None:
        raise HTTPException(status_code=404, detail="Video not found")
    runs = session.scalars(
        select(ModelRun).where(ModelRun.video_id == video_id, ModelRun.status == "COMPLETED")
    ).all()
    for model_run in runs:
        route_model_run_reviews(session, model_run)
    session.commit()
    items = session.scalars(
        select(ReviewItem)
        .where(ReviewItem.video_id == video_id, ReviewItem.status == "OPEN")
        .order_by(ReviewItem.created_at.desc())
    ).all()
    return [_review_response(session, item) for item in items]


@router.get("/videos/{video_id}/agreement", response_model=AgreementResponse)
def video_agreement(video_id: str, session: Session = Depends(get_session)):
    if session.get(Video, video_id) is None:
        raise HTTPException(status_code=404, detail="Video not found")
    annotations = session.scalars(
        select(Annotation).join(Frame).where(Frame.video_id == video_id)
    ).all()
    return AgreementResponse(video_id=video_id, **annotation_agreement(annotations))


@router.get("/dataset-health", response_model=DatasetHealthResponse)
def dataset_health(video_id: Optional[str] = None, session: Session = Depends(get_session)):
    if video_id and session.get(Video, video_id) is None:
        raise HTTPException(status_code=404, detail="Video not found")

    videos = list(
        session.scalars(select(Video).where(Video.id == video_id) if video_id else select(Video)).all()
    )
    frames_query = select(Frame)
    tasks_query = select(AnnotationTask)
    annotations_query = select(Annotation).join(Frame)
    predictions_query = select(ModelPrediction).join(Frame)
    reviews_query = select(ReviewItem)
    activities_query = select(AnnotationActivity).join(Frame)
    propagations_query = select(AnnotationPropagation).join(AnnotationTask)
    if video_id:
        frames_query = frames_query.where(Frame.video_id == video_id)
        tasks_query = tasks_query.where(AnnotationTask.video_id == video_id)
        annotations_query = annotations_query.where(Frame.video_id == video_id)
        predictions_query = predictions_query.where(Frame.video_id == video_id)
        reviews_query = reviews_query.where(ReviewItem.video_id == video_id)
        activities_query = activities_query.where(Frame.video_id == video_id)
        propagations_query = propagations_query.where(AnnotationTask.video_id == video_id)

    frames = list(session.scalars(frames_query).all())
    tasks = list(session.scalars(tasks_query).all())
    annotations = list(session.scalars(annotations_query).all())
    predictions = list(session.scalars(predictions_query).all())
    reviews = list(session.scalars(reviews_query).all())
    activities = list(session.scalars(activities_query).all())
    propagations = list(session.scalars(propagations_query).all())

    prediction_counts = Counter(prediction.status for prediction in predictions)
    decided = sum(prediction_counts[state] for state in ("ACCEPTED", "CORRECTED", "REJECTED"))
    durations = [activity.duration_ms for activity in activities if activity.duration_ms is not None]
    total_duration = sum(durations)
    annotated_count = sum(activity.annotation_count for activity in activities)
    agreement = annotation_agreement(annotations)

    return DatasetHealthResponse(
        video_id=video_id,
        videos=len(videos),
        frames=len(frames),
        annotated_frames=len({annotation.frame_id for annotation in annotations}),
        propagated_annotations=sum(annotation.propagation_id is not None for annotation in annotations),
        propagation_operations=len(propagations),
        reviewed_frames=len(
            {item.frame_id for item in reviews if item.status in {"RESOLVED", "ESCALATED"}}
        ),
        pending_tasks=sum(task.status != "COMPLETED" for task in tasks),
        completed_tasks=sum(task.status == "COMPLETED" for task in tasks),
        total_predictions=len(predictions),
        accepted_predictions=prediction_counts["ACCEPTED"],
        corrected_predictions=prediction_counts["CORRECTED"],
        rejected_predictions=prediction_counts["REJECTED"],
        pending_predictions=prediction_counts["PENDING"],
        model_acceptance_rate=prediction_counts["ACCEPTED"] / decided if decided else 0,
        model_correction_rate=prediction_counts["CORRECTED"] / decided if decided else 0,
        model_rejection_rate=prediction_counts["REJECTED"] / decided if decided else 0,
        low_confidence_predictions=sum(prediction.confidence < 0.5 for prediction in predictions),
        tracked_predictions=sum(prediction.track_id is not None for prediction in predictions),
        tracks=len(
            {
                (prediction.model_run_id, prediction.track_id)
                for prediction in predictions
                if prediction.track_id is not None
            }
        ),
        associated_snowboards=sum(
            prediction.label == "snowboard" and prediction.associated_prediction_id is not None
            for prediction in predictions
        ),
        unassociated_snowboards=sum(
            prediction.label == "snowboard" and prediction.associated_prediction_id is None
            for prediction in predictions
        ),
        open_review_items=sum(item.status == "OPEN" for item in reviews),
        resolved_review_items=sum(item.status == "RESOLVED" for item in reviews),
        average_annotation_time_ms=sum(durations) / len(durations) if durations else None,
        annotation_throughput_per_hour=(
            annotated_count / (total_duration / 3_600_000) if total_duration > 0 else None
        ),
        label_distribution=dict(Counter(annotation.label for annotation in annotations)),
        review_reason_distribution=dict(Counter(item.reason for item in reviews)),
        agreement=AgreementResponse(video_id=video_id, **agreement),
    )
