# Temporal sampling, tracking, and rider association

Milestone 4B turns independent frame predictions into an auditable temporal workflow. It addresses
two failures found in licensed real footage: 1 FPS sampling misses short actions, and mapping every
detected person to `rider` creates false semantics in crowded scenes.

## Sampling profiles

The upload API accepts multipart sampling controls:

- `overview`: 1 FPS for scene coverage and lower review cost
- `action`: 5 FPS for takeoff, rotation, landing, and short failure events
- `motion`: 1 FPS baseline plus 5 FPS bursts around high-change samples
- `custom`: an explicit `sample_fps` from 0.1 through 30

Motion-aware extraction analyzes a 64×36 grayscale stream at 5 FPS, measures mean absolute pixel
change, and retains a ±2-sample burst when change crosses the calibrated 0.75/255 threshold. Static regions
fall back to one frame per second. Stored timestamps remain tied to the original 5 FPS analysis
timeline, so variable-rate samples are auditable and seek correctly in the annotation workspace.

The chosen profile and resolved rate are stored on the video. Frame timestamps and extraction use
that stored rate, so retries and downstream audits reproduce the same sequence. The browser exposes
the overview and action profiles and includes the profile in its idempotency key.

## Temporal identities

Ultralytics runs ByteTrack over the ordered extracted frames. ByteTrack intentionally leaves some
low-confidence or short-lived detections unconfirmed, especially on sparse footage. A deterministic
geometry fallback fills those missing IDs using label-compatible IoU and center proximity over a
maximum three-sample gap. IDs from ByteTrack always take priority.

Each prediction stores `track_id`; each model run records
`ByteTrack+geometry-fallback-v1` in its parameters. This makes the tracker policy, model version,
confidence threshold, source video, and prediction geometry recoverable from the database.

## Person-to-board association

Detection preserves the pretrained `person` label first. On each frame, a one-to-one matcher scores
candidate snowboards using horizontal overlap, distance from the person's lower body, and horizontal
center proximity. A matched person becomes `rider`; both predictions store the other prediction ID,
the association score, and an ambiguity flag. The rider label is propagated only within the same
association-backed person track. Unmatched people remain `person`.

The quality router creates review items for unassociated snowboards, ambiguous associations, and
track gaps. The annotation workspace shows track and association provenance, while dataset health
reports track counts, tracked prediction volume, and linked/unlinked snowboards.

## Reviewer-controlled propagation

A reviewer can accept a tracked prediction or edit its box and propagate it over ±1, ±2, or ±5
sampled frames. Propagation uses each target frame's tracked geometry rather than copying one static
box. For a correction, the source frame's normalized position and size delta is applied to every
target and clamped to the image boundary.

The operation never replaces unrelated human annotations. It creates or updates only annotations
that reference predictions on the same model run and track. Every operation stores its source
prediction, source geometry, correction delta, frame range, reviewer, and generated count. Each
target prediction also receives a decision record, and generated annotations link back to the
propagation record.

## Current boundary

Track identity and semantic association remain model-generated proposals, not ground truth. A
versioned manifest and evaluator now exist, but the real clips still require a two-person annotation
and review pass before precision, recall, association accuracy, or ID-switch metrics can be claimed.
