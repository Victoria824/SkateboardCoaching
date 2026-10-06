from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import (
    Annotation,
    AnnotationActivity,
    AnnotationPropagation,
    AnnotationTask,
    Frame,
    ModelPrediction,
    ModelRun,
    PredictionDecision,
    ProcessingJob,
    Video,
)
from ..propagation import apply_bbox_delta, bbox_delta, has_correction
from ..schemas import (
    JobResponse,
    ModelMetricsResponse,
    ModelPredictionResponse,
    ModelRunCreatedResponse,
    ModelRunRequest,
    ModelRunResponse,
    PredictionDecisionResponse,
    PredictionRejectRequest,
    TrackPropagationRequest,
    TrackPropagationResponse,
)


router = APIRouter(prefix="/api", tags=["model-assisted labeling"])


def prediction_response(prediction: ModelPrediction) -> ModelPredictionResponse:
    return ModelPredictionResponse(
        id=prediction.id,
        model_run_id=prediction.model_run_id,
        frame_id=prediction.frame_id,
        label=prediction.label,
        confidence=prediction.confidence,
        annotation_type=prediction.annotation_type,
        geometry=prediction.geometry,
        track_id=prediction.track_id,
        associated_prediction_id=prediction.associated_prediction_id,
        association_score=prediction.association_score,
        association_ambiguous=prediction.association_ambiguous,
        status=prediction.status,
        model_name=prediction.model_run.model_name,
        model_version=prediction.model_run.model_version,
        created_at=prediction.created_at,
        resolved_at=prediction.resolved_at,
    )


@router.post("/videos/{video_id}/model-runs", response_model=ModelRunCreatedResponse, status_code=202)
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


@router.get("/model-runs/{model_run_id}", response_model=ModelRunResponse)
def get_model_run(model_run_id: str, session: Session = Depends(get_session)):
    model_run = session.get(ModelRun, model_run_id)
    if model_run is None:
        raise HTTPException(status_code=404, detail="Model run not found")
    return ModelRunResponse.model_validate(model_run)


@router.get("/videos/{video_id}/model-runs", response_model=List[ModelRunResponse])
def list_model_runs(video_id: str, session: Session = Depends(get_session)):
    if session.get(Video, video_id) is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return session.scalars(
        select(ModelRun)
        .where(ModelRun.video_id == video_id)
        .order_by(ModelRun.created_at.desc())
    ).all()


@router.get("/frames/{frame_id}/predictions", response_model=List[ModelPredictionResponse])
def list_predictions(frame_id: str, session: Session = Depends(get_session)):
    if session.get(Frame, frame_id) is None:
        raise HTTPException(status_code=404, detail="Frame not found")
    predictions = session.scalars(
        select(ModelPrediction)
        .where(ModelPrediction.frame_id == frame_id)
        .order_by(ModelPrediction.created_at)
    ).all()
    return [prediction_response(prediction) for prediction in predictions]


@router.post(
    "/predictions/{prediction_id}/reject",
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


@router.post(
    "/predictions/{prediction_id}/propagate",
    response_model=TrackPropagationResponse,
)
def propagate_prediction(
    prediction_id: str,
    request: TrackPropagationRequest,
    session: Session = Depends(get_session),
) -> TrackPropagationResponse:
    prediction = session.get(ModelPrediction, prediction_id)
    task = session.get(AnnotationTask, request.task_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if task is None or prediction.model_run.video_id != task.video_id:
        raise HTTPException(status_code=404, detail="Prediction does not belong to this task")
    if prediction.annotation_type != "bbox" or prediction.track_id is None:
        raise HTTPException(status_code=409, detail="Only tracked bounding boxes can be propagated")
    if not request.start_frame_number <= prediction.frame.frame_number <= request.end_frame_number:
        raise HTTPException(status_code=422, detail="Propagation range must include the source frame")

    delta = bbox_delta(prediction.geometry, request.geometry)
    corrected = has_correction(delta)
    target_predictions = list(
        session.scalars(
            select(ModelPrediction)
            .join(Frame)
            .where(
                ModelPrediction.model_run_id == prediction.model_run_id,
                ModelPrediction.track_id == prediction.track_id,
                ModelPrediction.annotation_type == "bbox",
                Frame.frame_number >= request.start_frame_number,
                Frame.frame_number <= request.end_frame_number,
            )
            .order_by(Frame.frame_number)
        ).all()
    )
    if not target_predictions:
        raise HTTPException(status_code=409, detail="No tracked predictions exist in this range")

    propagation = AnnotationPropagation(
        task_id=task.id,
        model_run_id=prediction.model_run_id,
        source_prediction_id=prediction.id,
        source_frame_id=prediction.frame_id,
        track_id=prediction.track_id,
        start_frame_number=request.start_frame_number,
        end_frame_number=request.end_frame_number,
        source_geometry=request.geometry,
        correction_delta=delta,
        reviewer=request.reviewer,
    )
    session.add(propagation)
    session.flush()

    annotations = []
    for target in target_predictions:
        geometry = apply_bbox_delta(target.geometry, delta)
        annotation = session.scalar(
            select(Annotation)
            .where(
                Annotation.task_id == task.id,
                Annotation.model_prediction_id == target.id,
            )
            .order_by(Annotation.created_at.desc())
            .limit(1)
        )
        if annotation is None:
            annotation = Annotation(
                task_id=task.id,
                frame_id=target.frame_id,
                label=prediction.label,
                annotation_type="bbox",
                geometry=geometry,
                source="track_propagated",
                model_prediction_id=target.id,
                propagation_id=propagation.id,
            )
            session.add(annotation)
        else:
            annotation.label = prediction.label
            annotation.geometry = geometry
            annotation.source = "track_propagated"
            annotation.propagation_id = propagation.id
        annotations.append((annotation, target))

    session.flush()
    decision_action = "PROPAGATED_CORRECTION" if corrected else "PROPAGATED_ACCEPTANCE"
    prediction_status = "CORRECTED" if corrected else "ACCEPTED"
    for annotation, target in annotations:
        target.status = prediction_status
        target.resolved_at = datetime.utcnow()
        session.add(
            PredictionDecision(
                prediction_id=target.id,
                task_id=task.id,
                annotation_id=annotation.id,
                action=decision_action,
                duration_ms=request.duration_ms,
            )
        )
    propagation.generated_count = len(annotations)
    session.add(
        AnnotationActivity(
            task_id=task.id,
            frame_id=prediction.frame_id,
            action="TRACK_PROPAGATE",
            duration_ms=request.duration_ms,
            annotation_count=len(annotations),
        )
    )
    if task.status == "PENDING":
        task.status = "IN_PROGRESS"
    session.commit()
    return TrackPropagationResponse(
        propagation_id=propagation.id,
        track_id=propagation.track_id,
        start_frame_number=propagation.start_frame_number,
        end_frame_number=propagation.end_frame_number,
        generated_count=propagation.generated_count,
        corrected=corrected,
        frame_ids=[target.frame_id for _, target in annotations],
    )


@router.get("/model-runs/{model_run_id}/metrics", response_model=ModelMetricsResponse)
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
