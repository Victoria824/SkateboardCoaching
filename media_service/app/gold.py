from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

from .quality import bbox_iou


def validate_gold_manifest(manifest: Dict[str, Any]) -> None:
    if manifest.get("schema_version") != "1.0":
        raise ValueError("Gold manifest schema_version must be 1.0")
    if not isinstance(manifest.get("videos"), list):
        raise ValueError("Gold manifest requires a videos array")
    for video in manifest["videos"]:
        source = video.get("source", {})
        if not source.get("sha256"):
            raise ValueError("Every gold video requires source.sha256")
        if not isinstance(video.get("frames"), list):
            raise ValueError("Every gold video requires a frames array")
        for frame in video["frames"]:
            if frame.get("review_status") not in {"pending", "approved"}:
                raise ValueError("Gold frames require pending or approved review_status")
            if not isinstance(frame.get("objects"), list):
                raise ValueError("Gold frames require an objects array")


def _prediction_reports_by_hash(reports: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    indexed = {}
    for report in reports:
        checksum = report.get("source", {}).get("sha256")
        if checksum:
            indexed[checksum] = report
    return indexed


def evaluate_gold_manifest(
    manifest: Dict[str, Any],
    prediction_reports: Iterable[Dict[str, Any]],
    iou_threshold: float = 0.5,
) -> Dict[str, Any]:
    validate_gold_manifest(manifest)
    if not 0 < iou_threshold <= 1:
        raise ValueError("IoU threshold must be between 0 and 1")
    reports_by_hash = _prediction_reports_by_hash(prediction_reports)
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    matched_ious: List[float] = []
    evaluated_frames = 0
    association_expected = 0
    association_evaluable = 0
    association_correct = 0

    for video in manifest["videos"]:
        checksum = video["source"]["sha256"]
        report = reports_by_hash.get(checksum)
        if report is None:
            raise ValueError("No prediction report found for gold video {}".format(checksum))
        detection_run = next(
            (run for run in report.get("runs", []) if run.get("model_kind") == "detection"),
            None,
        )
        if detection_run is None or "predictions" not in detection_run:
            raise ValueError(
                "Prediction report {} must be created with --include-predictions".format(checksum)
            )
        predictions_by_frame: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for prediction in detection_run["predictions"]:
            if prediction.get("annotation_type") == "bbox":
                predictions_by_frame[int(prediction["frame_number"])].append(prediction)

        for frame in video["frames"]:
            if frame["review_status"] != "approved":
                continue
            evaluated_frames += 1
            frame_number = int(frame["frame_number"])
            gold_objects = [
                item for item in frame["objects"] if item.get("annotation_type") == "bbox"
            ]
            predictions = predictions_by_frame.get(frame_number, [])
            labels = {item["label"] for item in gold_objects}.union(
                prediction["label"] for prediction in predictions
            )
            gold_to_prediction: Dict[str, Dict[str, Any]] = {}
            for label in labels:
                gold_for_label = [item for item in gold_objects if item["label"] == label]
                predictions_for_label = [
                    item for item in predictions if item["label"] == label
                ]
                candidates: List[Tuple[float, int, int]] = []
                for gold_index, gold in enumerate(gold_for_label):
                    for prediction_index, prediction in enumerate(predictions_for_label):
                        score = bbox_iou(gold["geometry"], prediction["geometry"])
                        if score >= iou_threshold:
                            candidates.append((score, gold_index, prediction_index))
                used_gold = set()
                used_predictions = set()
                for score, gold_index, prediction_index in sorted(candidates, reverse=True):
                    if gold_index in used_gold or prediction_index in used_predictions:
                        continue
                    used_gold.add(gold_index)
                    used_predictions.add(prediction_index)
                    matched_ious.append(score)
                    gold_to_prediction[gold_for_label[gold_index]["id"]] = predictions_for_label[
                        prediction_index
                    ]
                counts[label]["tp"] += len(used_gold)
                counts[label]["fn"] += len(gold_for_label) - len(used_gold)
                counts[label]["fp"] += len(predictions_for_label) - len(used_predictions)

            for gold in gold_objects:
                associated_id = gold.get("associated_object_id")
                if not associated_id:
                    continue
                association_expected += 1
                prediction = gold_to_prediction.get(gold["id"])
                associated_prediction = gold_to_prediction.get(associated_id)
                if prediction is None or associated_prediction is None:
                    continue
                association_evaluable += 1
                association_correct += (
                    prediction.get("associated_prediction_id") == associated_prediction.get("id")
                )

    if evaluated_frames == 0:
        raise ValueError("Gold manifest has no reviewer-approved frames")

    by_label = {}
    total_tp = total_fp = total_fn = 0
    for label, label_counts in sorted(counts.items()):
        tp, fp, fn = label_counts["tp"], label_counts["fp"], label_counts["fn"]
        total_tp += tp
        total_fp += fp
        total_fn += fn
        by_label[label] = {
            **label_counts,
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
        }
    return {
        "schema_version": "1.0",
        "iou_threshold": iou_threshold,
        "evaluated_frames": evaluated_frames,
        "overall": {
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
            "precision": total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0,
            "recall": total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0,
            "mean_matched_iou": (
                sum(matched_ious) / len(matched_ious) if matched_ious else None
            ),
        },
        "by_label": by_label,
        "association": {
            "expected": association_expected,
            "evaluable": association_evaluable,
            "correct": association_correct,
            "accuracy": (
                association_correct / association_evaluable if association_evaluable else None
            ),
        },
    }
