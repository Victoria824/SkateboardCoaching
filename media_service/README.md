# Snowboard Vision Media Service

This service is the canonical backend of the Snowboard Vision Data Platform. The optional
Node/Replicate coaching adapter consumes completed review output downstream.

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
- Uploads support `overview` (1 FPS), `action` (5 FPS), motion-aware 1–5 FPS bursts, and validated custom sampling rates.
- Detection and pose predictions retain temporal track IDs; person detections become riders only
  after a persisted snowboard association or association-backed track confirmation.
- Reviewers can propagate an accepted or corrected tracked box across a bounded frame range; every
  generated annotation and prediction decision links to an immutable propagation audit record.
- OpenCV proposes faces and license plates, YOLO proposes common screen devices, and geometry
  tracking assigns temporal PII identities. Every proposal is routed to human review.
- A completed privacy task with no unresolved PII proposals can queue an asynchronous FFmpeg
  sanitization job. Its manifest records reviewer, model versions, track IDs, checksums, duration,
  and failure state; completed outputs are downloadable as a bundle.
- Completed tasks export to COCO JSON or a YOLO image/label bundle.
- Every HTTP response carries `X-Request-ID`; `/api/operations/metrics` reports failure rate and
  per-job-type duration. Docker Compose starts two atomically claiming workers.
- Optional S3/MinIO mode provides signed direct uploads/downloads, local worker staging, persisted
  artifacts, and two-stage checksum verification. Worker leases recover jobs abandoned by a dead
  process after a bounded timeout.
- PII gold evaluation reports recall-weighted F2, difficult-case slices, false negatives per minute,
  uncovered-frame rate, temporal track coverage, and release-gating failures.
- A transactional job outbox publishes to Redis/Celery in deployed mode. Late-ack workers must win
  the same atomic database claim and lease used by the local polling worker, making duplicates safe.
- YOLO segmentation runs persist tracked snowboard polygons. Reviewers can accept/reject masks and
  export them in COCO or Ultralytics YOLO segmentation format.
- Accepted PII boxes become editable row-major RLE masks. FFmpeg merges blur through the reviewed
  pixels, then an independently trained, revision-pinned Grounding DINO post-render scan blocks
  release and records model provenance and findings in the audit manifest.

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

Compare PyTorch and ONNX Runtime on a real extracted frame:

```bash
.venv/bin/python scripts/benchmark_onnx.py data/media/frames/<video>/<frame>.jpg
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
| `MEDIA_STORAGE_BACKEND` | `local` | `local` or S3-compatible `s3` |
| `MEDIA_WORKER_LEASE_SECONDS` | `1800` | Time before another worker may reclaim an abandoned job |
| `MEDIA_QUEUE_BACKEND` | `database` | Local polling or deployed `celery` delivery |
| `MEDIA_REDIS_URL` | `redis://localhost:6379/0` | Celery broker URL |
| `MEDIA_RESIDUAL_PII_SCAN` | `true` | Require a zero-finding post-render scan before release |
| `MEDIA_RESIDUAL_PII_PROVIDER` | `grounding-dino` | Independent second-pass provider; `opencv-yolo` is a development fallback only |
| `MEDIA_RESIDUAL_PII_MODEL` | `IDEA-Research/grounding-dino-tiny` | Hugging Face checkpoint for residual detection |
| `MEDIA_RESIDUAL_PII_MODEL_REVISION` | pinned commit | Immutable checkpoint revision recorded in manifests |
| `MEDIA_RESIDUAL_PII_DEVICE` | `cpu` | Grounding DINO execution device (`cpu`, `mps`, or CUDA device) |
| `MEDIA_RESIDUAL_PII_SCAN_FPS` | `5` | Sanitized-video scan sampling rate |
| `MEDIA_RESIDUAL_PII_CONFIDENCE` | `0.25` | Fail-closed residual detector threshold |
| `MEDIA_RESIDUAL_PII_MASK_COVERAGE` | `0.8` | Coverage needed to classify a re-detection as protected |
| `S3_ENDPOINT_URL` | AWS default | MinIO/S3-compatible endpoint override |
| `S3_PUBLIC_ENDPOINT_URL` | internal endpoint | Browser-reachable endpoint used for signing URLs |
| `S3_BUCKET` | `snowboard-media` | Private media bucket |
| `S3_PRESIGN_TTL_SECONDS` | `900` | Direct-upload URL lifetime |
| `S3_PRESIGN_GET_TTL_SECONDS` | `3600` | Media download URL lifetime |
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
