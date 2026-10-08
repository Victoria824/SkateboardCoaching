from collections import defaultdict
import hashlib
import json
from typing import Any, Dict, Iterable, List, Tuple

from .quality import bbox_iou


PII_LABELS = {"face", "license_plate", "screen"}


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


def _f_score(precision: float, recall: float, beta: float) -> float:
    denominator = beta * beta * precision + recall
    return (
        (1 + beta * beta) * precision * recall / denominator
        if denominator
        else 0.0
    )


def evaluate_pii_gold_manifest(
    manifest: Dict[str, Any],
    prediction_reports: Iterable[Dict[str, Any]],
    iou_threshold: float = 0.5,
    recall_targets: Dict[str, float] = None,
    split_name: str = "test",
) -> Dict[str, Any]:
    """Evaluate privacy-critical detection and temporal coverage on approved gold frames."""
    validate_gold_manifest(manifest)
    if not 0 < iou_threshold <= 1:
        raise ValueError("IoU threshold must be between 0 and 1")
    targets = recall_targets or {"face": 0.98, "license_plate": 0.95, "screen": 0.95}
    reports_by_hash = _prediction_reports_by_hash(prediction_reports)
    counts = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    slice_counts = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    track_totals = defaultdict(int)
    track_matches = defaultdict(int)
    matched_ious = []
    evaluated_frames = 0
    frames_with_gold_pii = 0
    frames_with_uncovered_pii = 0
    evaluated_duration_ms = 0
    model_runs = []

    split_aware = any(video.get("split") for video in manifest["videos"])
    selected_videos = [
        video
        for video in manifest["videos"]
        if not split_aware or video.get("split") == split_name
    ]
    if not selected_videos:
        raise ValueError("Gold manifest has no videos in split {}".format(split_name))
    for video in selected_videos:
        checksum = video["source"]["sha256"]
        report = reports_by_hash.get(checksum)
        if report is None:
            raise ValueError("No prediction report found for gold video {}".format(checksum))
        pii_run = next(
            (run for run in report.get("runs", []) if run.get("model_kind") == "pii"),
            None,
        )
        if pii_run is None or "predictions" not in pii_run:
            raise ValueError(
                "Prediction report {} requires a PII run with --include-predictions".format(
                    checksum
                )
            )
        model_runs.append(
            {
                "source_sha256": checksum,
                "provider": pii_run.get("provider"),
                "model_name": pii_run.get("model_name"),
                "model_version": pii_run.get("model_version"),
                "model_revision": pii_run.get("model_revision"),
                "confidence_threshold": pii_run.get("confidence_threshold"),
                "device": pii_run.get("device"),
            }
        )
        evaluated_duration_ms += int((report.get("media") or {}).get("duration_ms") or 0)
        predictions_by_frame = defaultdict(list)
        for prediction in pii_run["predictions"]:
            if (
                prediction.get("annotation_type") == "bbox"
                and prediction.get("label") in PII_LABELS
            ):
                predictions_by_frame[int(prediction["frame_number"])].append(prediction)

        for frame in video["frames"]:
            if frame["review_status"] != "approved":
                continue
            evaluated_frames += 1
            gold_objects = [
                item
                for item in frame["objects"]
                if item.get("annotation_type") == "bbox" and item.get("label") in PII_LABELS
            ]
            predictions = predictions_by_frame.get(int(frame["frame_number"]), [])
            if gold_objects:
                frames_with_gold_pii += 1
            frame_missed = False
            tags = frame.get("difficult_case_tags") or ["all"]
            if "all" not in tags:
                tags = ["all", *tags]
            for label in PII_LABELS:
                gold_for_label = [item for item in gold_objects if item["label"] == label]
                predicted_for_label = [item for item in predictions if item["label"] == label]
                candidates = []
                for gold_index, gold in enumerate(gold_for_label):
                    for prediction_index, prediction in enumerate(predicted_for_label):
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
                tp = len(used_gold)
                fp = len(predicted_for_label) - len(used_predictions)
                fn = len(gold_for_label) - len(used_gold)
                counts[label]["tp"] += tp
                counts[label]["fp"] += fp
                counts[label]["fn"] += fn
                frame_missed = frame_missed or fn > 0
                for tag in tags:
                    slice_counts[tag]["tp"] += tp
                    slice_counts[tag]["fp"] += fp
                    slice_counts[tag]["fn"] += fn
                for index, gold in enumerate(gold_for_label):
                    track_id = gold.get("track_id")
                    if track_id is None:
                        continue
                    key = "{}:{}:{}".format(checksum, label, track_id)
                    track_totals[key] += 1
                    track_matches[key] += index in used_gold
            frames_with_uncovered_pii += frame_missed

    if evaluated_frames == 0:
        raise ValueError("Gold manifest has no reviewer-approved frames")

    def metrics(values):
        tp, fp, fn = values["tp"], values["fp"], values["fn"]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        return {
            **values,
            "precision": precision,
            "recall": recall,
            "f1": _f_score(precision, recall, 1),
            "f2": _f_score(precision, recall, 2),
        }

    by_label = {label: metrics(counts[label]) for label in sorted(PII_LABELS)}
    overall_counts = {
        key: sum(counts[label][key] for label in PII_LABELS) for key in ("tp", "fp", "fn")
    }
    gate_failures = [
        "{} recall {:.4f} is below {:.4f}".format(
            label, by_label[label]["recall"], target
        )
        for label, target in targets.items()
        if by_label[label]["tp"] + by_label[label]["fn"] > 0
        and by_label[label]["recall"] < target
    ]
    track_coverage = {
        track_id: track_matches[track_id] / total for track_id, total in track_totals.items()
    }
    duration_minutes = evaluated_duration_ms / 60_000
    return {
        "schema_version": "1.0",
        "evaluation_kind": "pii_detection",
        "dataset_name": (manifest.get("dataset") or {}).get("name"),
        "dataset_hash": hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "split": split_name if split_aware else "unspecified",
        "iou_threshold": iou_threshold,
        "recall_targets": targets,
        "evaluated_frames": evaluated_frames,
        "evaluated_duration_ms": evaluated_duration_ms,
        "frames_with_gold_pii": frames_with_gold_pii,
        "frames_with_uncovered_pii": frames_with_uncovered_pii,
        "uncovered_pii_frame_rate": (
            frames_with_uncovered_pii / frames_with_gold_pii if frames_with_gold_pii else 0.0
        ),
        "false_negatives_per_minute": (
            overall_counts["fn"] / duration_minutes if duration_minutes else None
        ),
        "mean_matched_iou": sum(matched_ious) / len(matched_ious) if matched_ious else None,
        "overall": metrics(overall_counts),
        "by_label": by_label,
        "by_difficult_case": {
            tag: metrics(values) for tag, values in sorted(slice_counts.items())
        },
        "tracks": {
            "count": len(track_coverage),
            "fully_covered": sum(value == 1 for value in track_coverage.values()),
            "mean_coverage": (
                sum(track_coverage.values()) / len(track_coverage) if track_coverage else None
            ),
            "coverage": track_coverage,
        },
        "model_runs": model_runs,
        "quality_gate": {"passed": not gate_failures, "failures": gate_failures},
    }


def evaluate_residual_pii_gold_manifest(
    manifest: Dict[str, Any],
    prediction_reports: Iterable[Dict[str, Any]],
    iou_threshold: float = 0.5,
    split_name: str = "test",
    max_miss_rate: float = 0.0,
) -> Dict[str, Any]:
    """Measure privacy leakage missed by the independent post-redaction detector.

    The gold source hashes must identify sanitized videos. A gold object means PII is still
    recognizable after rendering, so production defaults to a zero-false-negative gate.
    """
    if not 0 <= max_miss_rate <= 1:
        raise ValueError("Residual max miss rate must be between 0 and 1")
    normalized_reports = []
    for report in prediction_reports:
        normalized = dict(report)
        normalized["runs"] = [
            {**run, "model_kind": "pii"}
            for run in report.get("runs", [])
            if run.get("model_kind") == "residual_pii"
        ]
        normalized_reports.append(normalized)
    result = evaluate_pii_gold_manifest(
        manifest,
        normalized_reports,
        iou_threshold=iou_threshold,
        recall_targets={label: 1.0 for label in PII_LABELS},
        split_name=split_name,
    )
    gold_count = result["overall"]["tp"] + result["overall"]["fn"]
    miss_rate = result["overall"]["fn"] / gold_count if gold_count else 0.0
    leaking_frame_miss_rate = (
        result["frames_with_uncovered_pii"] / result["frames_with_gold_pii"]
        if result["frames_with_gold_pii"]
        else 0.0
    )
    failures = []
    if not gold_count:
        failures.append(
            "no reviewer-confirmed residual PII positives; detector miss rate is not measurable"
        )
    if result["overall"]["fn"] and miss_rate > max_miss_rate:
        failures.append(
            "residual PII miss rate {:.4f} exceeds {:.4f} ({} missed objects)".format(
                miss_rate, max_miss_rate, result["overall"]["fn"]
            )
        )
    result.update(
        {
            "evaluation_kind": "residual_pii_leakage",
            "max_miss_rate": max_miss_rate,
            "residual_pii_objects": gold_count,
            "residual_pii_missed": result["overall"]["fn"],
            "residual_miss_rate": miss_rate,
            "leaking_frame_miss_rate": leaking_frame_miss_rate,
            "quality_gate": {"passed": not failures, "failures": failures},
        }
    )
    return result
