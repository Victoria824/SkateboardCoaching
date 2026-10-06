# Production readiness evidence

## Implemented

- PostgreSQL-backed atomic job claiming supports multiple workers; Compose starts two workers.
- Request IDs, structured request duration logs, job failure rate, and per-type average duration.
- Local versioned Ultralytics/OpenCV inference and a reproducible PyTorch-versus-ONNX benchmark.
- Gold JSON, COCO JSON, YOLO ZIP, and sanitized MP4/manifest ZIP delivery formats.
- GitHub Actions validates migrations, backend tests, frontend tests, and the production build.

## Deliberate boundaries

- Storage is still local/shared-volume. Paths are storage keys, but an S3/MinIO adapter and signed
  URLs are not yet implemented.
- PostgreSQL is the queue authority. Redis/Celery is not added merely for branding; the current
  compare-and-swap claim supports safe horizontal workers, while leases and dead-worker recovery
  remain the next queue-hardening step.
- Bounding-box blur is implemented; pixel masks and snowboard/PII segmentation are not.
- The initial real-frame ONNX smoke benchmark is recorded in `docs/onnx-benchmark.md`; a larger
  gold-video benchmark is still required before making production-throughput claims.
