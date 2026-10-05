# Model-assisted labeling

Milestone 3 turns the annotation workspace into a human-in-the-loop computer-vision system. Model output is persisted as an immutable prediction; the annotator's decision and final annotation are stored separately.

## Workflow

```text
Processed frames
    -> asynchronous model run
    -> immutable model predictions
    -> annotation workspace
       -> accept  -> source=model annotation
       -> correct -> source=model_corrected annotation
       -> reject  -> decision event without annotation
    -> per-run quality and productivity metrics
```

Detection uses the lightweight Ultralytics YOLO model by default and keeps only `person` and `snowboard` detections. Person detections are normalized to the product label `rider`. Pose inference maps the model's COCO keypoints into the thirteen snowboard-workspace keypoints.

## Stored provenance

Every model run stores:

- provider, model name, model/runtime version, and device
- inference parameters
- total and processed frame counts
- lifecycle state and failure details
- measured end-to-end inference latency

Every prediction stores its original normalized geometry and confidence. Accepting or correcting does not overwrite that record.

## Workspace controls

- Amber dashed geometry: unresolved model prediction
- Green geometry: accepted model prediction
- Purple geometry: corrected model prediction
- `A`: accept selected prediction
- `C`: copy selected prediction into editable correction mode
- `R`: reject selected prediction

The metrics panel reports real acceptance, correction, and rejection rates plus average decision time. Runs with no predictions report zero values rather than fabricated demo metrics.

## Local ML setup

```bash
cd media_service
.venv/bin/pip install -r requirements-ml.txt
```

Model weights are downloaded by the upstream runtime on first use and are ignored by Git. Before commercial redistribution, review the selected model and runtime licenses.

## Verified smoke test

On 2026-10-05, an Apple Silicon CPU smoke test processed two 640×360 synthetic video frames with `yolo11n.pt` and Ultralytics 8.4.173. The recorded inference latency was 1001 ms. The synthetic test pattern contained no person or snowboard, so the correct recorded prediction count was zero.

Unit and API tests use a deterministic provider and never require model downloads. This keeps CI repeatable while the explicit ML smoke test verifies the real adapter.

