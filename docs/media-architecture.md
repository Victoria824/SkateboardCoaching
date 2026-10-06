# Media ingestion architecture

```text
React reviewer UI
  → FastAPI canonical API → PostgreSQL/SQLite audit records
                         ↘ local/S3-compatible storage boundary
  → worker: FFmpeg → YOLO/OpenCV → tracking → review queue
  → human approval → COCO/YOLO or sanitized MP4 + manifest

Legacy Node/Replicate coach
  → consumes completed FastAPI COCO review output for provenance-backed reports
  → downstream narrative demo only; never owns canonical labels or privacy state
```

## Service boundaries

- FastAPI owns upload validation, persistence, status APIs, idempotency, and media URLs.
- The worker owns CPU-heavy media commands and state transitions.
- Storage paths are persisted as keys relative to a configured root, so local storage can later be replaced by S3-compatible object storage without changing API records.
- The legacy Node backend owns only the optional coaching/chat demo. Its placeholder-frame path has
  been removed. `POST /api/coaching/reviewed/{task_id}` consumes only completed FastAPI review
  output and returns its task/video provenance; all canonical data-platform work belongs in FastAPI.

## State model

```text
QUEUED
  -> PROCESSING_VIDEO
  -> EXTRACTING_FRAMES
  -> READY_FOR_ANNOTATION

On a media error:
  -> RETRY_PENDING (up to max_attempts)
  -> FAILED
```

Each job records attempts, progress, stable error code, human-readable failure detail, and lifecycle timestamps. Upload clients can supply `Idempotency-Key` to safely repeat a request.

## Current scope and deliberate limits

- Development defaults to SQLite; Docker Compose runs PostgreSQL.
- Files use a shared local volume. An S3 adapter and presigned direct uploads are the next storage step.
- The worker polls the database. Redis/Celery is intentionally deferred until workload evidence justifies it.
- Overview/action/custom sampling and motion-aware bursts persist source timestamps. Scene and
  keyframe policies remain future sampling options.
- Schema changes are managed through Alembic and CI verifies the migration head.
