# Review workflow and dataset health

Milestone 4A adds a persisted quality-control loop around model-assisted annotation. It turns model
uncertainty and detector disagreement into explicit work for a reviewer, records every resolution,
and exposes dataset-level health metrics in the browser at `/#/quality`.

```text
Detection / pose run
        ↓
Deterministic routing rules
        ↓
Persisted review item ──→ reviewer action ──→ immutable review event
        ↓                                      ↓
Open review queue                       dataset-health metrics
```

## Automatic routing

Completed inference runs are checked for:

- confidence below 0.50
- boxes touching the image boundary
- same-label boxes with IoU of at least 0.85
- rider detections with no pose on the same frame
- poses with no rider detection on the same frame
- deterministic 5% random audit sampling

Each item stores the source video, frame, model run, prediction, reason, severity, score, routing
details, status, and timestamps. A stable deduplication key makes routing idempotent.

## Review actions

The quality dashboard supports:

- **Approve** — confirm that the routed item is valid
- **Correct** — mark it for correction and open the associated annotation task
- **Escalate** — retain it for specialist review
- **Dismiss** — close a false alarm or irrelevant routing reason

Actions create separate review-event records with reviewer and optional notes. Predictions remain
immutable, preserving model provenance.

## Agreement and health metrics

Multiple annotation tasks can now be created for the same video with `force_new=true`. Dataset
health compares matching labels across annotators using greedy one-to-one matching:

- bounding boxes: mean intersection over union (IoU)
- keypoints: percentage of common visible points within a normalized 0.05 distance threshold

The dashboard also reports annotation coverage, reviewed frames, task status, model decisions,
low-confidence volume, review-reason distribution, time per save, and annotations per hour.

## API

```text
GET  /api/dataset-health
GET  /api/dataset-health?video_id={video_id}
GET  /api/review-items?status=OPEN
POST /api/review-items/{review_item_id}/resolve
POST /api/videos/{video_id}/review-items/route
GET  /api/videos/{video_id}/agreement
POST /api/videos/{video_id}/annotation-tasks?force_new=true&assigned_to={name}
```

## Real-video routing check

The licensed clips from the real-video evaluation were rerun through the complete routing path:

| Clip | Predictions | Review items | Reasons |
| --- | ---: | ---: | --- |
| Crowded resort POV | 70 | 39 | 20 low confidence, 9 edge clipped, 6 missing pose, 4 random audit |
| Single-rider jump | 16 | 14 | 9 low confidence, 3 missing pose, 1 edge clipped, 1 pose without rider |

These counts are routing workload, not error counts. Human review or gold annotations are required
to determine whether an item is a true model failure.

## Remaining Milestone 4 work

Milestone 4B should add configurable 5 FPS and motion-aware sampling, temporal track IDs,
person-to-snowboard association, box propagation, and a versioned gold-label manifest. Those
features will turn the current frame-level quality loop into a complete temporal review workflow.
