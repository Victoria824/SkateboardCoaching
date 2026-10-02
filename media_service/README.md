# Snowboard Vision Media Service

This service is the first infrastructure slice of the Snowboard Vision Data Platform. It preserves the existing Node coaching backend while introducing a reliable, asynchronous path for video ingestion and real frame extraction.

## What it provides

- `POST /api/videos` streams an uploaded video to storage and returns `202 Accepted`.
- `GET /api/jobs/{job_id}` reports explicit processing state, progress, attempts, and failure details.
- A separate worker runs `ffprobe` and FFmpeg outside the request lifecycle.
- Video metadata, jobs, and timestamped frame records are persisted with SQLAlchemy.
- `GET /api/videos/{video_id}` and `/frames` expose processed metadata and frame URLs.
- `Idempotency-Key` prevents a client retry from creating duplicate work.
- Failed work records a stable error code and can be retried.

SQLite is the zero-setup development default. Set `MEDIA_DATABASE_URL` to a PostgreSQL URL for a deployed environment.

## Run locally

```bash
cd media_service
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# Terminal 1
.venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 2
.venv/bin/python -m app.worker
```

Open `http://localhost:8000/docs` to exercise the API.

```bash
curl -i -X POST http://localhost:8000/api/videos \
  -H 'Idempotency-Key: demo-upload-1' \
  -F 'video=@ride.mp4'
```

For the PostgreSQL-backed stack, run from the repository root:

```bash
docker compose up --build
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `MEDIA_DATABASE_URL` | local SQLite file | SQLAlchemy database URL |
| `MEDIA_STORAGE_ROOT` | `media_service/data/media` | Local object-storage root |
| `MEDIA_MAX_UPLOAD_BYTES` | 250 MiB | Upload limit |
| `MEDIA_FRAME_SAMPLE_FPS` | `1` | Extracted frames per second |
| `MEDIA_WORKER_POLL_SECONDS` | `1` | Worker polling interval |
| `MEDIA_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `FFMPEG_BINARY` | `ffmpeg` | FFmpeg executable |
| `FFPROBE_BINARY` | `ffprobe` | ffprobe executable |

## Test

```bash
.venv/bin/pytest -q
```
