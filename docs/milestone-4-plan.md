# Milestone 4 plan: temporal review and dataset health

## Status

Milestones 4A, 4B, and the first 4C slice are implemented through temporal correction: IoU/PCK agreement primitives,
automatic review routing, the `/quality` dashboard, 1 FPS/5 FPS sampling profiles, persisted track
IDs, ByteTrack plus deterministic geometry fallback, explicit person-to-board association,
reviewer-controlled correction propagation, a versioned gold-label evaluator, and motion-aware
1–5 FPS burst sampling. Remaining 4C work is the human labeling pass and exact clip boundaries.

## Objective

Turn the current frame-by-frame model-assisted labeling demo into a reviewable temporal data
workflow that measures quality on real snowboarding footage. This milestone directly targets the
role's human-in-the-loop tooling, video infrastructure, annotation quality, and practical CV
service requirements.

The real-video evaluation found three connected gaps: the 1 FPS sampler misses short actions,
independent detections have no temporal identity, and the current metrics measure reviewer actions
without measuring prediction accuracy. Milestone 4 should close that loop before adding PII blur
or inference optimization.

## Workstream 1 — Ground-truth evaluation set

Create a small, versioned benchmark manifest from redistributable or locally licensed videos.
Media remains outside Git; the manifest stores source, license evidence, hash, clip boundaries,
sampling policy, and annotator/reviewer status.

Build a gold-label workflow for approximately 50–100 representative frames:

- rider and snowboard boxes
- person activity label: snowboarder, skier, bystander, unknown
- person-to-board association
- 13 rider keypoints with visibility
- difficult-case tags such as tiny subject, edge clipping, occlusion, airborne, and motion blur

Report detection precision/recall and IoU against this set. Report keypoint coverage and normalized
distance/PCK-style agreement. Do not treat `frames_with_predictions` as recall.

## Workstream 2 — Temporal sampling and tracks

Replace the single global sample rate with explicit sampling profiles:

- 1 FPS overview
- 5 FPS action labeling
- motion-aware bursts around high-change regions
- optional exact clip boundaries

Add a track data model and a practical tracker such as ByteTrack. Predictions should carry a
stable `track_id`, and the UI should support propagating an accepted/corrected box across adjacent
frames. A person can only become a `rider` when associated with a snowboard track or confirmed by
a reviewer.

The first implementation may run tracking in the existing Python worker. It should record model,
tracker, parameters, latency, and source run IDs so the result remains auditable.

## Workstream 3 — Automatic review routing

Add persisted review items with reason, severity, status, assignee, and resolution event. Initial
routing rules should include:

- confidence below a configurable threshold
- detector finds a rider but pose is missing
- pose exists without a compatible rider box
- duplicate boxes with high overlap
- box clipped at the image boundary
- track disappears and reappears unexpectedly
- person/board association is ambiguous
- configurable random audit sample, initially 5%

The review UI should provide previous/current/next frames, prediction provenance, track context,
and keyboard actions for approve, correct, reject, and escalate.

## Workstream 4 — Dataset health dashboard

Add dataset-level queries and a React dashboard for:

- frames annotated and reviewed
- pending and overdue review items
- model acceptance/correction/rejection rates
- low-confidence and missing-pose rates
- ground-truth IoU and keypoint agreement
- label and difficult-case distribution
- annotation and review throughput
- metrics split by model version, label, sampling profile, and source video

Each metric must link back to the underlying examples so the dashboard supports debugging rather
than displaying unexplained aggregates.

## Workstream 5 — Reliability and evidence

- Add Alembic migrations and indexes for tracks, review items, and audit events.
- Add unit tests for IoU, PCK-style agreement, association, routing rules, and audit sampling.
- Add an end-to-end real-fixture test: ingest, infer, track, annotate, route, review, and measure.
- Record request IDs, job IDs, model/tracker versions, and stage durations in structured logs.
- Capture product screenshots and update the repository's architecture and interview narrative.

## Definition of done

Milestone 4 is complete when:

1. A licensed real-video evaluation manifest can be reproduced without committing source media.
2. Fast motion can be processed with a selectable or motion-aware sampling profile.
3. Rider predictions have stable temporal tracks and explicit board association.
4. A correction can be propagated and then audited across a short sequence.
5. Low-quality and randomly sampled items enter a persisted review queue automatically.
6. Bounding-box and keypoint agreement are tested and visible in the dashboard.
7. All published quality and latency numbers come from saved evaluation artifacts.

## Recommended implementation order

1. Evaluation manifest, gold annotations, IoU/PCK metrics
2. Sampling profiles and track schema
3. Tracking and person-to-board association
4. Review routing and reviewer workspace
5. Dataset health dashboard and end-to-end evidence

After this milestone, the next role-aligned step should be the PII detection, tracking, review, and
sanitized-export pipeline. The tracking and review foundations built here will be reused directly.
