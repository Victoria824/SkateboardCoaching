import hashlib
import math
from collections import defaultdict
from itertools import combinations
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Annotation, ModelPrediction, ModelRun, ReviewItem


def bbox_iou(first: Dict[str, Any], second: Dict[str, Any]) -> float:
    first_right = float(first["x"]) + float(first["width"])
    first_bottom = float(first["y"]) + float(first["height"])
    second_right = float(second["x"]) + float(second["width"])
    second_bottom = float(second["y"]) + float(second["height"])
    intersection_width = max(
        0.0, min(first_right, second_right) - max(float(first["x"]), float(second["x"]))
    )
    intersection_height = max(
        0.0, min(first_bottom, second_bottom) - max(float(first["y"]), float(second["y"]))
    )
    intersection = intersection_width * intersection_height
    union = (
        float(first["width"]) * float(first["height"])
        + float(second["width"]) * float(second["height"])
        - intersection
    )
    return intersection / union if union > 0 else 0.0


def keypoint_pck(
    first: Dict[str, Any], second: Dict[str, Any], threshold: float = 0.05
) -> Optional[float]:
    first_points = {
        point["name"]: point
        for point in first.get("points", [])
        if point.get("visible", True)
    }
    second_points = {
        point["name"]: point
        for point in second.get("points", [])
        if point.get("visible", True)
    }
    names = sorted(set(first_points).intersection(second_points))
    if not names:
        return None
    matched = 0
    for name in names:
        left, right = first_points[name], second_points[name]
        distance = math.hypot(float(left["x"]) - float(right["x"]), float(left["y"]) - float(right["y"]))
        matched += distance <= threshold
    return matched / len(names)


def is_edge_clipped(geometry: Dict[str, Any], margin: float = 0.01) -> bool:
    x, y = float(geometry["x"]), float(geometry["y"])
    right = x + float(geometry["width"])
    bottom = y + float(geometry["height"])
    return x <= margin or y <= margin or right >= 1 - margin or bottom >= 1 - margin


def deterministic_audit(identifier: str, percentage: float) -> bool:
    bucket = int(hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return bucket < percentage / 100


def _add_review(
    session: Session,
    model_run: ModelRun,
    prediction: ModelPrediction,
    reason: str,
    severity: str,
    score: Optional[float] = None,
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    dedupe_key = ":".join((model_run.id, prediction.frame_id, prediction.id, reason))
    if session.scalar(select(ReviewItem.id).where(ReviewItem.dedupe_key == dedupe_key)):
        return False
    session.add(
        ReviewItem(
            dedupe_key=dedupe_key,
            video_id=model_run.video_id,
            frame_id=prediction.frame_id,
            model_run_id=model_run.id,
            prediction_id=prediction.id,
            reason=reason,
            severity=severity,
            score=score,
            details=details or {},
        )
    )
    return True


def route_model_run_reviews(
    session: Session,
    model_run: ModelRun,
    low_confidence_threshold: float = 0.5,
    duplicate_iou_threshold: float = 0.85,
    audit_percentage: float = 5.0,
) -> int:
    predictions = list(
        session.scalars(
            select(ModelPrediction).where(ModelPrediction.model_run_id == model_run.id)
        ).all()
    )
    created = 0
    for prediction in predictions:
        if model_run.model_kind == "pii":
            created += _add_review(
                session,
                model_run,
                prediction,
                "PII_APPROVAL_REQUIRED",
                "HIGH",
                prediction.confidence,
                {"track_id": prediction.track_id, "label": prediction.label},
            )
        if prediction.confidence < low_confidence_threshold:
            created += _add_review(
                session,
                model_run,
                prediction,
                "LOW_CONFIDENCE",
                "MEDIUM",
                prediction.confidence,
                {"threshold": low_confidence_threshold},
            )
        if prediction.annotation_type == "bbox" and is_edge_clipped(prediction.geometry):
            created += _add_review(
                session, model_run, prediction, "EDGE_CLIPPED", "HIGH", details={"margin": 0.01}
            )
        if prediction.label == "snowboard" and prediction.associated_prediction_id is None:
            created += _add_review(
                session,
                model_run,
                prediction,
                "UNASSOCIATED_SNOWBOARD",
                "HIGH",
                details={"expected_label": "rider"},
            )
        if prediction.association_ambiguous:
            created += _add_review(
                session,
                model_run,
                prediction,
                "AMBIGUOUS_BOARD_ASSOCIATION",
                "MEDIUM",
                prediction.association_score,
            )
        if deterministic_audit(prediction.id, audit_percentage):
            created += _add_review(
                session,
                model_run,
                prediction,
                "RANDOM_AUDIT",
                "LOW",
                details={"audit_percentage": audit_percentage},
            )

    grouped: Dict[Tuple[str, str], List[ModelPrediction]] = defaultdict(list)
    for prediction in predictions:
        if prediction.annotation_type == "bbox":
            grouped[(prediction.frame_id, prediction.label)].append(prediction)
    for frame_predictions in grouped.values():
        for first, second in combinations(frame_predictions, 2):
            overlap = bbox_iou(first.geometry, second.geometry)
            if overlap < duplicate_iou_threshold:
                continue
            lower_confidence = min((first, second), key=lambda item: item.confidence)
            created += _add_review(
                session,
                model_run,
                lower_confidence,
                "DUPLICATE_OVERLAP",
                "HIGH",
                overlap,
                {"other_prediction_id": first.id if lower_confidence.id == second.id else second.id},
            )

    predictions_by_track: Dict[str, List[ModelPrediction]] = defaultdict(list)
    for prediction in predictions:
        if prediction.track_id is not None:
            predictions_by_track[prediction.track_id].append(prediction)
    for track_id, track_predictions in predictions_by_track.items():
        ordered = sorted(track_predictions, key=lambda item: item.frame.frame_number)
        for previous, current in zip(ordered, ordered[1:]):
            gap = current.frame.frame_number - previous.frame.frame_number
            if gap <= 1:
                continue
            created += _add_review(
                session,
                model_run,
                current,
                "TRACK_GAP",
                "MEDIUM",
                details={
                    "track_id": track_id,
                    "previous_frame_number": previous.frame.frame_number,
                    "current_frame_number": current.frame.frame_number,
                    "missing_sampled_frames": gap - 1,
                },
            )

    completed_runs = list(
        session.scalars(
            select(ModelRun).where(
                ModelRun.video_id == model_run.video_id,
                ModelRun.status == "COMPLETED",
            )
        ).all()
    )
    detection_runs = [run for run in completed_runs if run.model_kind == "detection"]
    pose_runs = [run for run in completed_runs if run.model_kind == "pose"]
    if detection_runs and pose_runs:
        latest_detection = max(detection_runs, key=lambda run: run.created_at)
        latest_pose = max(pose_runs, key=lambda run: run.created_at)
        rider_predictions = list(
            session.scalars(
                select(ModelPrediction).where(
                    ModelPrediction.model_run_id == latest_detection.id,
                    ModelPrediction.label == "rider",
                )
            ).all()
        )
        pose_predictions = list(
            session.scalars(
                select(ModelPrediction).where(ModelPrediction.model_run_id == latest_pose.id)
            ).all()
        )
        riders_by_frame: Dict[str, List[ModelPrediction]] = defaultdict(list)
        poses_by_frame: Dict[str, List[ModelPrediction]] = defaultdict(list)
        for prediction in rider_predictions:
            riders_by_frame[prediction.frame_id].append(prediction)
        for prediction in pose_predictions:
            poses_by_frame[prediction.frame_id].append(prediction)
        for frame_id in set(riders_by_frame).difference(poses_by_frame):
            prediction = max(riders_by_frame[frame_id], key=lambda item: item.confidence)
            created += _add_review(
                session,
                latest_detection,
                prediction,
                "MISSING_POSE",
                "HIGH",
                prediction.confidence,
            )
        for frame_id in set(poses_by_frame).difference(riders_by_frame):
            prediction = max(poses_by_frame[frame_id], key=lambda item: item.confidence)
            created += _add_review(
                session,
                latest_pose,
                prediction,
                "POSE_WITHOUT_RIDER",
                "HIGH",
                prediction.confidence,
            )
    session.flush()
    return created


def annotation_agreement(annotations: Iterable[Annotation]) -> Dict[str, Any]:
    by_frame_and_task: Dict[str, Dict[str, List[Annotation]]] = defaultdict(lambda: defaultdict(list))
    for annotation in annotations:
        by_frame_and_task[annotation.frame_id][annotation.task_id].append(annotation)

    bbox_scores: List[float] = []
    keypoint_scores: List[float] = []
    for task_groups in by_frame_and_task.values():
        for first_group, second_group in combinations(task_groups.values(), 2):
            keys = {(item.annotation_type, item.label) for item in first_group}.intersection(
                (item.annotation_type, item.label) for item in second_group
            )
            for annotation_type, label in keys:
                first_candidates = [
                    item
                    for item in first_group
                    if item.annotation_type == annotation_type and item.label == label
                ]
                second_candidates = [
                    item
                    for item in second_group
                    if item.annotation_type == annotation_type and item.label == label
                ]
                scored_pairs = []
                for first_index, first in enumerate(first_candidates):
                    for second_index, second in enumerate(second_candidates):
                        score = (
                            bbox_iou(first.geometry, second.geometry)
                            if annotation_type == "bbox"
                            else keypoint_pck(first.geometry, second.geometry)
                        )
                        if score is not None:
                            scored_pairs.append((score, first_index, second_index))
                used_first = set()
                used_second = set()
                for score, first_index, second_index in sorted(scored_pairs, reverse=True):
                    if first_index in used_first or second_index in used_second:
                        continue
                    used_first.add(first_index)
                    used_second.add(second_index)
                    if annotation_type == "bbox":
                        bbox_scores.append(score)
                    else:
                        keypoint_scores.append(score)
    return {
        "bbox_comparisons": len(bbox_scores),
        "mean_bbox_iou": sum(bbox_scores) / len(bbox_scores) if bbox_scores else None,
        "keypoint_comparisons": len(keypoint_scores),
        "mean_keypoint_pck": (
            sum(keypoint_scores) / len(keypoint_scores) if keypoint_scores else None
        ),
    }
