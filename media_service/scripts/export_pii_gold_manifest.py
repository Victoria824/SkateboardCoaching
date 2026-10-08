#!/usr/bin/env python3
"""Export a completed privacy annotation task into a reviewer-approved gold manifest."""

import argparse
from datetime import datetime
import json
import sys
from pathlib import Path

from sqlalchemy import select


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.gold import PII_LABELS, validate_gold_manifest  # noqa: E402
from app.models import Annotation, AnnotationTask, ModelPrediction  # noqa: E402
from app.privacy import sha256_file  # noqa: E402
from app.storage import create_storage  # noqa: E402


ALLOWED_DIFFICULT_TAGS = {
    "crowded",
    "edge_entry",
    "low_light",
    "motion_blur",
    "occluded",
    "positive_control",
    "profile_face",
    "reflection",
    "screen_glare",
    "small_object",
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-name", default="snowboard-pii-gold-v1")
    parser.add_argument("--guidelines-version", default="1.0")
    parser.add_argument("--annotator", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--split", choices=("train", "validation", "test"), required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-creator", required=True)
    parser.add_argument("--source-license", required=True)
    parser.add_argument(
        "--tags",
        type=Path,
        help='Optional JSON object mapping frame numbers to tag arrays, e.g. {"12":["low_light"]}',
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append this video to an existing output manifest",
    )
    return parser.parse_args()


def normalized_bbox(annotation: Annotation):
    geometry = annotation.geometry
    if annotation.annotation_type == "mask":
        geometry = geometry.get("bbox")
    if annotation.annotation_type not in {"bbox", "mask"} or not geometry:
        raise ValueError("PII annotation {} has no exportable bbox".format(annotation.id))
    bbox = {name: float(geometry[name]) for name in ("x", "y", "width", "height")}
    if (
        bbox["width"] <= 0
        or bbox["height"] <= 0
        or any(value < 0 or value > 1 for value in bbox.values())
        or bbox["x"] + bbox["width"] > 1.000001
        or bbox["y"] + bbox["height"] > 1.000001
    ):
        raise ValueError("PII annotation {} has invalid normalized geometry".format(annotation.id))
    return bbox


def main():
    args = parse_args()
    annotator = args.annotator.strip()
    reviewer = args.reviewer.strip()
    if not annotator or not reviewer:
        raise SystemExit("Annotator and reviewer are required")
    if annotator.casefold() == reviewer.casefold():
        raise SystemExit("Annotator and reviewer must be different people")
    tags = json.loads(args.tags.read_text(encoding="utf-8")) if args.tags else {}
    if (
        not isinstance(tags, dict)
        or any(not isinstance(value, list) for value in tags.values())
        or any(not isinstance(tag, str) for values in tags.values() for tag in values)
    ):
        raise SystemExit("--tags must contain a JSON object whose values are arrays")
    unknown_tags = sorted(
        {tag for values in tags.values() for tag in values} - ALLOWED_DIFFICULT_TAGS
    )
    if unknown_tags:
        raise SystemExit("Unknown difficult-case tags: {}".format(", ".join(unknown_tags)))

    storage = create_storage()
    with SessionLocal() as session:
        task = session.get(AnnotationTask, args.task_id)
        if task is None:
            raise SystemExit("Annotation task does not exist: {}".format(args.task_id))
        if task.status != "COMPLETED":
            raise SystemExit("Complete and review the annotation task before gold export")
        video = task.video
        frame_numbers = {str(frame.frame_number) for frame in video.frames}
        unknown_frames = sorted(set(tags) - frame_numbers)
        if unknown_frames:
            raise SystemExit(
                "Tag sidecar references unknown frames: {}".format(", ".join(unknown_frames))
            )
        annotations = list(
            session.scalars(
                select(Annotation)
                .where(
                    Annotation.task_id == task.id,
                    Annotation.label.in_(PII_LABELS),
                )
                .order_by(Annotation.frame_id, Annotation.created_at)
            ).all()
        )
        predictions = {
            prediction.id: prediction
            for prediction in session.scalars(
                select(ModelPrediction).where(
                    ModelPrediction.id.in_(
                        [item.model_prediction_id for item in annotations if item.model_prediction_id]
                    )
                )
            ).all()
        }
        by_frame = {}
        for annotation in annotations:
            prediction = predictions.get(annotation.model_prediction_id)
            track_id = (
                prediction.track_id
                if prediction and prediction.track_id is not None
                else annotation.propagation.track_id if annotation.propagation else None
            )
            item = {
                "id": annotation.id,
                "label": annotation.label,
                "annotation_type": "bbox",
                "geometry": normalized_bbox(annotation),
            }
            if track_id is not None:
                item["track_id"] = str(track_id)
            by_frame.setdefault(annotation.frame_id, []).append(item)

        source_path = storage.absolute_path(video.storage_path)
        source_hash = video.source_sha256 or sha256_file(source_path)
        video_manifest = {
            "source": {
                "sha256": source_hash,
                "url": args.source_url,
                "creator": args.source_creator,
                "license": args.source_license,
            },
            "sampling_profile": video.sampling_profile,
            "split": args.split,
            "sample_fps": video.sample_fps,
            "frames": [
                {
                    "frame_number": frame.frame_number,
                    "timestamp_ms": frame.timestamp_ms,
                    "review_status": "approved",
                    "annotator": annotator,
                    "reviewer": reviewer,
                    "difficult_case_tags": tags.get(str(frame.frame_number), []),
                    "objects": by_frame.get(frame.id, []),
                }
                for frame in video.frames
            ],
        }

    if args.append:
        if not args.output.exists():
            raise SystemExit("--append requires an existing output manifest")
        manifest = json.loads(args.output.read_text(encoding="utf-8"))
        if any(item["source"]["sha256"] == source_hash for item in manifest.get("videos", [])):
            raise SystemExit("Output manifest already contains source {}".format(source_hash))
        manifest["videos"].append(video_manifest)
    else:
        if args.output.exists():
            raise SystemExit("Output already exists; use --append or choose another path")
        manifest = {
            "schema_version": "1.0",
            "dataset": {
                "name": args.dataset_name,
                "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "guidelines_version": args.guidelines_version,
            },
            "videos": [video_manifest],
        }
    validate_gold_manifest(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        "Exported {} approved frames and {} PII objects to {}".format(
            len(video_manifest["frames"]), len(annotations), args.output
        )
    )


if __name__ == "__main__":
    main()
