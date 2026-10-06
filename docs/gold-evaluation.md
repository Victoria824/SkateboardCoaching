# Gold-label evaluation workflow

The real-video smoke benchmark proves that the production path runs, but prediction counts are not
accuracy. This workflow separates frame selection, annotation, review, and metric publication so an
unreviewed frame can never silently become ground truth.

## Versioned manifest

[`gold_manifest.schema.json`](../media_service/evaluation/gold_manifest.schema.json) defines version
1.0. Each video records its source URL, creator, permission evidence, SHA-256 checksum, sampling
profile, and exact sample rate. Each selected frame records:

- frame number and timestamp
- `pending` or `approved` review status
- annotator, reviewer, and difficult-case tags
- person, rider, snowboard, or pose objects
- normalized geometry, temporal track identity, and optional person-to-board association

The checked-in [`gold_manifest.template.json`](../media_service/evaluation/gold_manifest.template.json)
contains the licensed jump video's provenance but deliberately contains no approved labels. Source
media remains ignored and is never redistributed.

## Scoring contract

Generate predictions with full geometry:

```bash
cd media_service
.venv/bin/python scripts/evaluate_pipeline.py /licensed/video.mp4 \
  --sample-fps 5 \
  --include-predictions \
  --output data/evaluation/predictions.json
```

After two-person annotation and review, run:

```bash
.venv/bin/python scripts/evaluate_gold.py \
  evaluation/gold_manifest.json \
  data/evaluation/predictions.json \
  --iou-threshold 0.5 \
  --output data/evaluation/gold-metrics.json
```

The evaluator matches boxes greedily by video checksum, approved frame, and label. It reports TP,
FP, FN, precision, recall, and mean matched IoU overall and by label. Association accuracy is scored
only when both linked gold objects have matched predictions. Pending frames are ignored; a manifest
with no approved frames fails instead of producing misleading zeroes.

## Publication gate

Do not publish accuracy from the template. A valid benchmark release requires at least one annotator
and a separate reviewer, resolved disagreements, recorded guidelines version, unchanged source
checksums, and saved prediction reports from a named model/tracker version. ID switches and pose PCK
remain the next evaluator extensions after the first reviewed detection set is complete.
