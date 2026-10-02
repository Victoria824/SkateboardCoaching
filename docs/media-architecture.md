# Media ingestion architecture

```text
React client
    |
    | POST /api/videos (streamed upload)
    v
FastAPI media service ------> shared object/local storage
    |
    | creates video + QUEUED job, returns 202
    v
PostgreSQL / SQLite (development)
    ^
    | atomically claims job
Python media worker
    |
    +--> ffprobe metadata
    +--> FFmpeg frame extraction
    +--> timestamped frame records
    |
    v
READY_FOR_ANNOTATION
```

## Service boundaries

- FastAPI owns upload validation, persistence, status APIs, idempotency, and media URLs.
- The worker owns CPU-heavy media commands and state transitions.
- Storage paths are persisted as keys relative to a configured root, so local storage can later be replaced by S3-compatible object storage without changing API records.
- The legacy Node backend continues to own the coaching/chat experience during migration.

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
- Frame timestamps are derived from the configured constant sampling rate. Variable-rate, scene-based, and keyframe sampling will require timestamp extraction from FFmpeg output.
- Schema creation currently uses SQLAlchemy metadata. Alembic migrations are required before a shared production deployment.

