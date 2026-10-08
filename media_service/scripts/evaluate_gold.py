#!/usr/bin/env python3
"""Score saved prediction reports against reviewer-approved gold frames."""

import argparse
import json
import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.gold import (  # noqa: E402
    evaluate_gold_manifest,
    evaluate_pii_gold_manifest,
    evaluate_residual_pii_gold_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("prediction_reports", type=Path, nargs="+")
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument(
        "--mode", choices=("general", "pii", "residual-pii"), default="general"
    )
    parser.add_argument("--split", default="test", help="PII dataset split to evaluate")
    parser.add_argument(
        "--max-residual-miss-rate",
        type=float,
        default=0.0,
        help="Release threshold for residual PII; production default is zero",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    reports = [
        json.loads(path.read_text(encoding="utf-8")) for path in args.prediction_reports
    ]
    if args.mode == "residual-pii":
        result = evaluate_residual_pii_gold_manifest(
            manifest,
            reports,
            args.iou_threshold,
            split_name=args.split,
            max_miss_rate=args.max_residual_miss_rate,
        )
    elif args.mode == "pii":
        result = evaluate_pii_gold_manifest(
            manifest, reports, args.iou_threshold, split_name=args.split
        )
    else:
        result = evaluate_gold_manifest(manifest, reports, args.iou_threshold)
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
