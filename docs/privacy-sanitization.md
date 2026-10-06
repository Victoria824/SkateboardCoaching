# Privacy review and sanitized video export

Milestone 5A reuses the annotation and worker infrastructure for privacy-safe dataset delivery.
Reviewers can draw bounding boxes with the labels `face`, `license_plate`, and `screen`, then queue
an asynchronous sanitized export from the annotation workspace.

```text
PII annotations
      ↓
Persisted export request and job
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
- each source annotation ID and PII label
- time interval and pixel geometry for every blur segment
- export/job status, errors, and completion time

The MP4 and manifest are stored under an export-specific directory and exposed through the media
service only after successful completion. A failed job keeps its stable error code and does not
claim a valid output.

## API

```text
POST /api/videos/{video_id}/sanitized-exports
GET  /api/sanitized-exports/{export_id}
GET  /api/videos/{video_id}/sanitized-exports
```

The create request accepts an annotation task ID and an optional subset of `face`, `license_plate`,
and `screen`. A request with no matching reviewed regions is rejected instead of producing an
apparently sanitized but unchanged video.

## Current boundary

Milestone 5A deliberately starts with reviewer-authored regions so the export and audit contract is
trustworthy. The next slice should add model-generated face, plate, and screen proposals, temporal
tracking, uncertainty routing, and an explicit reviewer approval gate before export. Automated PII
detection must be measured against approved gold labels before it is described as privacy complete.
