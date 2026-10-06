# Privacy review and sanitized video export

Milestone 5A reuses the annotation and worker infrastructure for privacy-safe dataset delivery.
Reviewers can draw bounding boxes with the labels `face`, `license_plate`, and `screen`, then queue
an asynchronous sanitized export from the annotation workspace.

```text
OpenCV/YOLO PII proposals → temporal tracks → mandatory human decisions
      ↓
Completed annotation task + named reviewer export gate
      ↓
Time-bounded FFmpeg crop → blur → overlay chain
      ↓
Sanitized MP4 + audit manifest + SHA-256
```

## Temporal behavior

Each reviewed frame owns the interval halfway to its previous and next sampled timestamps. This
works with fixed-rate and motion-aware sampling and prevents the export from assuming a constant
frame interval. Normalized boxes are converted to clamped pixel regions using the original video
dimensions. FFmpeg crops only the selected region, applies blur, overlays it during that interval,
copies the original audio stream when present, and strips source metadata and chapters from the
export.

## Audit manifest

Every completed export records:

- source video, annotation task, selected labels, and annotation count
- source and output SHA-256 checksums
- detector provider, model name/version, parameters, and blurred track IDs
- named reviewer and exact processing duration
- each source annotation ID and PII label
- time interval and pixel geometry for every blur segment
- export/job status, errors, and completion time

The MP4 and manifest are stored under an export-specific directory and exposed through the media
service only after successful completion. A failed job writes a failure manifest with its stable
error code, reviewer, timestamp, and processing duration, but never claims a valid video output.

## API

```text
POST /api/videos/{video_id}/sanitized-exports
GET  /api/sanitized-exports/{export_id}
GET  /api/videos/{video_id}/sanitized-exports
GET  /api/sanitized-exports/{export_id}/bundle
```

The create request accepts a completed annotation task ID, named reviewer, and an optional subset
of `face`, `license_plate`, and `screen`. It is rejected when matching regions are absent or any PII
prediction remains unresolved.

## Detection boundary

The default local provider uses OpenCV Haar cascades for faces and license plates and maps YOLO
`tv`, `laptop`, and `cell phone` detections to `screen`. These are proposals, never automatic blur
decisions. Production claims still require evaluation against reviewer-approved PII gold labels;
custom trained weights can replace the screen model through `MEDIA_PII_SCREEN_MODEL`.
