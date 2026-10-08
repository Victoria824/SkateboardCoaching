#!/usr/bin/env python3
"""Run the independent residual-PII detector on one sanitized video."""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from time import perf_counter


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.config import settings  # noqa: E402
from app.inference import create_residual_pii_provider  # noqa: E402
from app.media import FFmpegProcessor  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Sanitized video to scan")
    parser.add_argument("--sample-fps", type=float, default=settings.residual_pii_scan_fps)
    parser.add_argument("--confidence", type=float, default=settings.residual_pii_confidence)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    args = parse_args()
    video = args.video.expanduser().resolve()
    if not video.is_file():
        raise SystemExit("Video does not exist: {}".format(video))
    if not 0 < args.sample_fps <= 30:
        raise SystemExit("--sample-fps must be between 0 and 30")
    if not 0 <= args.confidence <= 1:
        raise SystemExit("--confidence must be between 0 and 1")
    processor = FFmpegProcessor()
    metadata = processor.probe(video)
    provider = create_residual_pii_provider()
    started = perf_counter()
    with tempfile.TemporaryDirectory(prefix="residual-pii-evaluation-") as directory:
        frames = processor.extract_frames(video, Path(directory), args.sample_fps)
        outputs_by_frame = provider.infer_frames(
            frames, "pii", args.confidence, settings.residual_pii_device
        )
    predictions = []
    for frame_number, outputs in enumerate(outputs_by_frame, start=1):
        for output in outputs:
            predictions.append(
                {
                    "frame_number": frame_number,
                    "timestamp_ms": round((frame_number - 1) * 1000 / args.sample_fps),
                    "label": output.label,
                    "confidence": round(output.confidence, 6),
                    "annotation_type": output.annotation_type,
                    "geometry": output.geometry,
                }
            )
    wall_ms = round((perf_counter() - started) * 1000)
    report = {
        "source": {"filename": video.name, "sha256": sha256(video)},
        "media": {
            "duration_ms": metadata.duration_ms,
            "width": metadata.width,
            "height": metadata.height,
            "fps": metadata.fps,
            "sample_fps": args.sample_fps,
            "sampled_frame_count": len(outputs_by_frame),
        },
        "runs": [
            {
                "model_kind": "residual_pii",
                "provider": getattr(provider, "provider_name", provider.__class__.__name__),
                "model_name": getattr(provider, "model_name", None),
                "model_revision": getattr(provider, "model_revision", None),
                "model_version": provider.runtime_version,
                "device": settings.residual_pii_device,
                "confidence_threshold": args.confidence,
                "processed_frames": len(outputs_by_frame),
                "wall_latency_ms": wall_ms,
                "milliseconds_per_frame": round(wall_ms / max(1, len(outputs_by_frame)), 2),
                "predictions": predictions,
            }
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
