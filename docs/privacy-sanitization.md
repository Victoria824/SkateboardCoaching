# Privacy review and sanitized video export

The privacy workflow reuses the annotation and worker infrastructure for fail-closed dataset
delivery. Reviewers accept conservative proposals for `face`, `license_plate`, and `screen`, refine
individual mask pixels with paint/erase brushes, then queue an asynchronous sanitized export.

```text
OpenCV/YOLO PII boxes → padded RLE mask → paint/erase review
      ↓
Completed annotation task + named reviewer export gate
      ↓
Time-bounded FFmpeg pixel mask → masked blur merge
      ↓
Residual-PII detector → pass: release / finding: fail closed
      ↓
Sanitized MP4 + audit manifest + SHA-256 (passed scans only)
```

## Mask and temporal behavior

Accepted PII proposals become padded 128×128 row-major RLE masks. The reviewer can add or erase
pixels with an adjustable brush; edit count and final edit mode remain in the saved geometry. Empty
masks are rejected. Legacy reviewed boxes remain supported as conservative full-rectangle masks.

Each reviewed frame owns the interval halfway to its previous and next sampled timestamps. At
render time, mask grid runs are expanded outward to original-video pixels. FFmpeg blurs the full
frame once and uses the time-bounded mask to merge only reviewed pixels. It preserves optional audio
while stripping source metadata and chapters.

## Residual-PII release gate

After rendering, the service samples the output at `MEDIA_RESIDUAL_PII_SCAN_FPS` and runs a
separate Grounding DINO open-vocabulary detector. This Transformer detector is independent of the
OpenCV Haar/Ultralytics first pass, and its Hugging Face model commit is pinned and recorded. A
face, plate, or screen proposal with less than 80% reviewed-mask coverage produces
`RESIDUAL_PII_DETECTED`; covered re-detections are retained separately in the manifest so device
outline detections do not permanently block screen sanitization. Failed video is deleted from
staging and never gains a public storage key. Only a zero-uncovered-finding scan can reach
`COMPLETED` and become downloadable.

Disabling `MEDIA_RESIDUAL_PII_SCAN` is supported for local diagnostics and is recorded as `SKIPPED`.
It should not be disabled for privacy-sensitive delivery.

## Audit manifest

Every completed export records:

- source video, annotation task, selected labels, and annotation count
- source and output SHA-256 checksums
- detector provider, model name/version, parameters, and blurred track IDs
- named reviewer and exact processing duration
- mask encoding, dimensions, coverage, edit count, and time interval
- residual scanner version, threshold, sampled frames, and findings
- export/job status, errors, and completion time

A failed job writes a private failure manifest with its stable error code, reviewer, residual
findings, timestamp, and duration, but never claims a valid video output.

## API

```text
POST /api/videos/{video_id}/sanitized-exports
GET  /api/sanitized-exports/{export_id}
GET  /api/videos/{video_id}/sanitized-exports
GET  /api/sanitized-exports/{export_id}/bundle
```

The create request accepts a completed annotation task ID, named reviewer, and an optional subset
of supported PII labels. It is rejected when matching regions are absent or any PII prediction
remains unresolved.

## Detection boundary

The first-pass provider uses OpenCV Haar cascades for faces and license plates and maps YOLO `tv`,
`laptop`, and `cell phone` detections to `screen`. These remain proposals rather than automatic
privacy decisions. The residual gate uses revision-pinned Grounding DINO with explicit face, plate,
monitor, laptop, and smartphone prompts. Independence reduces correlated blind spots but does not
prove zero PII; the reviewer-confirmed residual-video gold gate remains mandatory before production.
