#!/usr/bin/env python3
"""Run the real media and inference workers against a local video.

The evaluator deliberately uses an isolated SQLite database and media directory,
so benchmark runs cannot modify the developer's application data.
"""

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Iterable, List

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.database import Base  # noqa: E402
from app.inference import UltralyticsProvider  # noqa: E402
from app.models import (  # noqa: E402
    Frame,
    ModelPrediction,
    ModelRun,
    ProcessingJob,
    ReviewItem,
    Video,
)
from app.service import claim_next_job, process_inference_job, process_job  # noqa: E402
from app.storage import LocalStorage  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the real FFmpeg and Ultralytics pipeline on one video."
    )
    parser.add_argument("video", type=Path, help="Path to a local video file")
    parser.add_argument(
        "--model-kind",
        action="append",
        choices=("detection", "pose"),
        dest="model_kinds",
        help="Model to run; repeat for both. Defaults to detection and pose.",
    )
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument(
        "--sample-fps",
        type=float,
        default=1.0,
        help="Frame sampling rate. Use 1 for overview or 5 for action labeling.",
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--source-url")
    parser.add_argument("--source-creator")
    parser.add_argument("--source-license")
    parser.add_argument(
        "--include-predictions",
        action="store_true",
        help="Include every prediction geometry in addition to aggregate metrics.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return round(ordered[index], 4)


def prediction_summary(
    predictions: List[ModelPrediction], include_predictions: bool = False
) -> Dict[str, Any]:
    confidences = [prediction.confidence for prediction in predictions]
    by_label = Counter(prediction.label for prediction in predictions)
    by_frame = Counter(prediction.frame.frame_number for prediction in predictions)
    track_ids = {prediction.track_id for prediction in predictions if prediction.track_id is not None}
    track_lengths = Counter(
        prediction.track_id for prediction in predictions if prediction.track_id is not None
    )
    summary = {
        "prediction_count": len(predictions),
        "frames_with_predictions": len(by_frame),
        "predictions_by_label": dict(sorted(by_label.items())),
        "tracked_predictions": sum(prediction.track_id is not None for prediction in predictions),
        "track_count": len(track_ids),
        "multi_frame_tracks": sum(length > 1 for length in track_lengths.values()),
        "associated_snowboards": sum(
            prediction.label == "snowboard" and prediction.associated_prediction_id is not None
            for prediction in predictions
        ),
        "unassociated_snowboards": sum(
            prediction.label == "snowboard" and prediction.associated_prediction_id is None
            for prediction in predictions
        ),
        "confidence": {
            "min": round(min(confidences), 4) if confidences else None,
            "median": percentile(confidences, 0.5) if confidences else None,
            "max": round(max(confidences), 4) if confidences else None,
        },
    }
    if include_predictions:
        summary["predictions"] = [
            {
                "id": prediction.id,
                "frame_number": prediction.frame.frame_number,
                "timestamp_ms": prediction.frame.timestamp_ms,
                "label": prediction.label,
                "confidence": round(prediction.confidence, 4),
                "annotation_type": prediction.annotation_type,
                "geometry": prediction.geometry,
                "track_id": prediction.track_id,
                "associated_prediction_id": prediction.associated_prediction_id,
                "association_score": prediction.association_score,
                "association_ambiguous": prediction.association_ambiguous,
            }
            for prediction in predictions
        ]
    return summary


def run_evaluation(args: argparse.Namespace) -> Dict[str, Any]:
    source = args.video.expanduser().resolve()
    if not source.is_file():
        raise SystemExit("Video does not exist: {}".format(source))
    if not 0 < args.confidence <= 1:
        raise SystemExit("--confidence must be between 0 and 1")
    if not 0.1 <= args.sample_fps <= 30:
        raise SystemExit("--sample-fps must be between 0.1 and 30")

    model_kinds = args.model_kinds or ["detection", "pose"]
    with tempfile.TemporaryDirectory(prefix="snowboard-evaluation-") as temp_directory:
        work_directory = Path(temp_directory)
        engine = create_engine("sqlite:///{}".format(work_directory / "evaluation.db"))
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        storage = LocalStorage((work_directory / "media").resolve())

        with Session() as session:
            video = Video(
                filename=source.name,
                storage_path="pending",
                mime_type="video/{}".format(source.suffix.lstrip(".") or "unknown"),
                file_size=source.stat().st_size,
                sampling_profile=(
                    "action"
                    if args.sample_fps == 5
                    else "overview" if args.sample_fps == 1 else "custom"
                ),
                sample_fps=args.sample_fps,
                status="QUEUED",
            )
            session.add(video)
            session.flush()
            stored_source = storage.video_path(video.id, source.name)
            stored_source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, stored_source)
            video.storage_path = storage.relative_path(stored_source)
            ingestion_job = ProcessingJob(
                video=video,
                job_type="VIDEO_INGESTION",
                state="QUEUED",
            )
            session.add(ingestion_job)
            session.commit()

            ingestion_started = perf_counter()
            claimed_job_id = claim_next_job(session)
            process_job(session, claimed_job_id, storage=storage)
            ingestion_wall_ms = round((perf_counter() - ingestion_started) * 1000)
            session.refresh(video)
            session.refresh(ingestion_job)
            if ingestion_job.state != "READY_FOR_ANNOTATION":
                raise RuntimeError(
                    "Video ingestion failed: {} {}".format(
                        ingestion_job.error_code, ingestion_job.error_message
                    )
                )

            report: Dict[str, Any] = {
                "source": {
                    "filename": source.name,
                    "sha256": sha256(source),
                    "size_bytes": source.stat().st_size,
                    "url": args.source_url,
                    "creator": args.source_creator,
                    "license": args.source_license,
                },
                "media": {
                    "duration_ms": video.duration_ms,
                    "width": video.width,
                    "height": video.height,
                    "fps": video.fps,
                    "codec": video.codec,
                    "source_frame_count": video.source_frame_count,
                    "sampled_frame_count": len(video.frames),
                    "sampling_profile": video.sampling_profile,
                    "sample_fps": video.sample_fps,
                    "sample_interval_ms": (
                        video.frames[1].timestamp_ms - video.frames[0].timestamp_ms
                        if len(video.frames) > 1
                        else None
                    ),
                    "ingestion_wall_ms": ingestion_wall_ms,
                },
                "runs": [],
            }

            for model_kind in model_kinds:
                model_filename = "yolo11n-pose.pt" if model_kind == "pose" else "yolo11n.pt"
                local_model = SERVICE_ROOT / model_filename
                provider = UltralyticsProvider(
                    str(local_model) if local_model.exists() else model_filename
                )
                model_run = ModelRun(
                    video=video,
                    model_kind=model_kind,
                    provider="ultralytics",
                    model_name=model_filename,
                    model_version="pretrained",
                    device=args.device,
                    parameters={"confidence_threshold": args.confidence},
                    status="QUEUED",
                    total_frames=len(video.frames),
                )
                inference_job = ProcessingJob(
                    video=video,
                    model_run=model_run,
                    job_type="MODEL_INFERENCE",
                    state="QUEUED",
                )
                session.add_all([model_run, inference_job])
                session.commit()

                inference_started = perf_counter()
                claimed_job_id = claim_next_job(session)
                process_inference_job(
                    session,
                    claimed_job_id,
                    provider=provider,
                    storage=storage,
                )
                inference_wall_ms = round((perf_counter() - inference_started) * 1000)
                session.refresh(model_run)
                session.refresh(inference_job)
                if inference_job.state != "COMPLETED":
                    raise RuntimeError(
                        "{} inference failed: {} {}".format(
                            model_kind,
                            inference_job.error_code,
                            inference_job.error_message,
                        )
                    )
                predictions = list(
                    session.scalars(
                        select(ModelPrediction)
                        .join(Frame)
                        .where(ModelPrediction.model_run_id == model_run.id)
                        .order_by(Frame.frame_number, ModelPrediction.confidence.desc())
                    ).all()
                )
                report["runs"].append(
                    {
                        "model_kind": model_kind,
                        "model_name": model_run.model_name,
                        "model_version": model_run.model_version,
                        "device": model_run.device,
                        "confidence_threshold": args.confidence,
                        "processed_frames": model_run.processed_frames,
                        "worker_latency_ms": model_run.latency_ms,
                        "wall_latency_ms": inference_wall_ms,
                        "milliseconds_per_frame": round(
                            inference_wall_ms / max(1, model_run.processed_frames), 2
                        ),
                        **prediction_summary(predictions, args.include_predictions),
                    }
                )
            review_items = list(session.scalars(select(ReviewItem)).all())
            report["review_queue"] = {
                "total": len(review_items),
                "by_reason": dict(sorted(Counter(item.reason for item in review_items).items())),
                "by_severity": dict(
                    sorted(Counter(item.severity for item in review_items).items())
                ),
            }
            return report


def main() -> None:
    args = parse_args()
    report = run_evaluation(args)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
