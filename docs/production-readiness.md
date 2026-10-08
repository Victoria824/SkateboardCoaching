# Production readiness evidence

## Implemented

- PostgreSQL-backed atomic job claiming supports multiple workers; Compose starts two workers.
- Request IDs, structured request duration logs, job failure rate, and per-type average duration.
- Local versioned Ultralytics/OpenCV inference and a reproducible PyTorch-versus-ONNX benchmark.
- Gold JSON, COCO JSON, YOLO ZIP, and sanitized MP4/manifest ZIP delivery formats.
- GitHub Actions validates migrations, backend tests, frontend tests, and the production build.
- Private S3/MinIO storage supports signed browser upload, signed download, worker staging, artifact
  persistence, size/checksum validation, and a second worker-side source checksum verification.
- Worker leases, heartbeats, bounded attempts, and expired-worker recovery prevent abandoned jobs
  from remaining permanently active.
- A transactional PostgreSQL outbox, Redis broker, and late-acknowledgement Celery workers provide
  at-least-once distributed delivery; compare-and-swap claims make duplicate messages harmless.
- PII proposals become editable RLE pixel masks; FFmpeg performs masked blur and a post-render
  residual-PII scan blocks release whenever the detector finds a possible region.
- The independent Grounding DINO adapter has completed a real local frame/video smoke test with a
  pinned checkpoint; see `docs/residual-pii-smoke.md`.

## Deliberate boundaries

- Local storage remains available for zero-setup development; the S3 path still needs a live MinIO
  Compose smoke test on a host with Docker and production IAM/encryption configuration.
- Redis/Celery Compose execution still needs a live Docker fault-injection smoke test. Production
  also requires broker TLS/authentication, managed failover, and a dead-letter administration path.
- The demo API has no tenant authentication or role-based authorization. Signed object URLs limit
  bucket exposure but do not replace API auth, reviewer identity, or per-project access control.
- Snowboard instance segmentation and PII pixel-mask review are implemented. The residual gate now
  uses a revision-pinned Grounding DINO detector independent of the OpenCV/YOLO first pass. A real
  reviewer-confirmed residual-video gold report is still required; the evaluator intentionally
  refuses to call a zero-positive dataset a measured production pass.
- The initial real-frame ONNX smoke benchmark is recorded in `docs/onnx-benchmark.md`; a larger
  gold-video benchmark is still required before making production-throughput claims.
