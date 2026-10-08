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
run an independent Grounding DINO residual scan and fail closed on any finding.

## Residual-video gold gate

Residual labels must describe the **rendered sanitized video**, not the original upload. Use the
same 5 FPS extraction order as the release gate. Include clean negative frames plus positive leakage
controls (for example, deliberately under-masked copies kept only in the private evaluation set),
otherwise detector recall and miss rate cannot be measured. Two people should approve every
positive control. Never ship the positive-control artifact.

Start from `evaluation/residual_gold_manifest.template.json`, replace the source hash with the
sanitized file's SHA-256, and label every still-recognizable `face`, `license_plate`, and `screen`.
Then create independent-model predictions and score them:

```bash
.venv/bin/python scripts/evaluate_residual_pipeline.py /path/to/sanitized.mp4 \
  --sample-fps 5 --output data/evaluation/residual-report.json

.venv/bin/python scripts/evaluate_gold.py \
  evaluation/residual_gold_manifest.json data/evaluation/residual-report.json \
  --mode residual-pii --split test --max-residual-miss-rate 0 \
  --output data/evaluation/residual-gold-metrics.json
```

The production gate is zero missed reviewer-confirmed residual objects. The report includes object
miss rate, leaking-frame miss rate, false negatives per minute, difficult-case slices, exact model
revision, and the gold dataset hash. A dataset without positive leakage controls fails with “not
measurable”; it is useful for false-positive analysis but cannot establish residual recall.
