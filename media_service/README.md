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
- Annotation-task endpoints persist normalized boxes, keypoints, task state, and time-per-frame activity.
- Completed model runs automatically route uncertain or inconsistent predictions to review.
- Dataset-health endpoints report annotation coverage, review status, IoU/PCK agreement, and throughput.
- Uploads support `overview` (1 FPS), `action` (5 FPS), and validated custom sampling rates.
- Detection and pose predictions retain temporal track IDs; person detections become riders only
  after a persisted snowboard association or association-backed track confirmation.
- Reviewers can propagate an accepted or corrected tracked box across a bounded frame range; every
  generated annotation and prediction decision links to an immutable propagation audit record.

SQLite is the zero-setup development default. Set `MEDIA_DATABASE_URL` to a PostgreSQL URL for a deployed environment.

## Run locally

```bash
cd media_service
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head

# Terminal 1
.venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 2
.venv/bin/python -m app.worker
```

Install the optional real-model runtime before running detection or pose inference:

```bash
.venv/bin/pip install -r requirements-ml.txt
```

## Real-video evaluation

Run the production FFmpeg and Ultralytics workers against a licensed local video without touching
the development database:

```bash
.venv/bin/python scripts/evaluate_pipeline.py /path/to/video.mp4 \
  --sample-fps 5 \
  --source-url "https://source.example/video" \
  --source-creator "Creator name" \
  --source-license "License or permission evidence" \
  --output data/evaluation/report.json
```

The source video, extracted frames, and JSON output belong under the ignored `data/` directory.
See [the real-video findings](../docs/real-video-evaluation.md) for the recorded methodology and
results.

Create a report with `--include-predictions`, then score only reviewer-approved gold frames:

```bash
.venv/bin/python scripts/evaluate_gold.py \
  evaluation/gold_manifest.json \
  data/evaluation/report.json \
  --output data/evaluation/gold-metrics.json
```

The schema and starter manifest live in `evaluation/`. See
[the gold evaluation workflow](../docs/gold-evaluation.md).

Database schema changes are managed exclusively by Alembic. API and worker startup never mutate
the schema. Docker Compose runs the migration automatically before starting either process.

Open `http://localhost:8000/docs` to exercise the API.

```bash
curl -i -X POST http://localhost:8000/api/videos \
  -H 'Idempotency-Key: demo-upload-1' \
  -F 'sampling_profile=action' \
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
| `MEDIA_FRAME_SAMPLE_FPS` | `1` | Legacy fallback when a stored video has no sample rate |
| `MEDIA_WORKER_POLL_SECONDS` | `1` | Worker polling interval |
| `MEDIA_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `FFMPEG_BINARY` | `ffmpeg` | FFmpeg executable |
| `FFPROBE_BINARY` | `ffprobe` | ffprobe executable |

## Test

```bash
.venv/bin/pytest -q
```
