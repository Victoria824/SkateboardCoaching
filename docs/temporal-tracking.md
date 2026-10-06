# Temporal sampling, tracking, and rider association

Milestone 4B turns independent frame predictions into an auditable temporal workflow. It addresses
two failures found in licensed real footage: 1 FPS sampling misses short actions, and mapping every
detected person to `rider` creates false semantics in crowded scenes.

## Sampling profiles

The upload API accepts multipart sampling controls:

- `overview`: 1 FPS for scene coverage and lower review cost
- `action`: 5 FPS for takeoff, rotation, landing, and short failure events
- `custom`: an explicit `sample_fps` from 0.1 through 30

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

## Current boundary

Track identity and semantic association are model-generated proposals, not ground truth. The next
slice should let a reviewer propagate a corrected box over a selected frame range and persist every
generated annotation with its source prediction, track, range, and reviewer action. A versioned
gold-label manifest is still required to measure precision, recall, association accuracy, and ID
switches.
