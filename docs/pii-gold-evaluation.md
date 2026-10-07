# PII gold evaluation

The privacy quality gate scores only reviewer-approved frames and, when the manifest declares
splits, evaluates the frozen `test` split by default. Videos—not adjacent frames—must be assigned to
`train`, `validation`, or `test` to prevent temporal leakage.

Gold objects may use `face`, `license_plate`, and `screen`, normalized bounding boxes, and optional
track IDs. `difficult_case_tags` should capture slices such as `motion_blur`, `low_light`,
`small_object`, `occluded`, and `edge_entry`.

Run real PII inference with saved predictions:

```bash
.venv/bin/python scripts/evaluate_pipeline.py /path/to/video.mp4 \
  --model-kind pii --include-predictions \
  --source-url "..." --source-creator "..." --source-license "..." \
  --output data/evaluation/pii-report.json
```

Evaluate the frozen test split:

```bash
.venv/bin/python scripts/evaluate_gold.py \
  evaluation/gold_manifest.json data/evaluation/pii-report.json \
  --mode pii --split test --output data/evaluation/pii-gold-metrics.json
```

The report includes per-class precision, recall, F1, recall-weighted F2, mean matched IoU,
false-negatives per video minute, frames containing uncovered PII, difficult-case metrics, temporal
track coverage, model provenance, dataset hash, and a recall quality gate. Default targets are 98%
for faces and 95% for plates and screens. A target is skipped only when the selected split contains
no gold objects for that class.

Passing this detector gate is necessary but not sufficient for a privacy claim. Sanitized exports
now run an automated residual-PII scan and fail closed on any finding. Before a production claim,
measure that scan against a separate reviewer-confirmed residual-video gold set and preferably use
an independent model so first-pass and second-pass blind spots are not identical.
