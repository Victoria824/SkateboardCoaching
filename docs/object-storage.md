# S3/MinIO storage and signed uploads

Set `MEDIA_STORAGE_BACKEND=s3` to use private S3-compatible object storage. Workers retain a local
staging directory for FFmpeg and model libraries, while the object bucket remains the shared source
of truth. Missing inputs are downloaded on demand; extracted frames, manifests, and sanitized videos
are uploaded before their database records are committed.

The direct upload protocol is:

```text
POST /api/direct-uploads
  → short-lived presigned PUT + required Content-Type/SHA-256 metadata headers
browser PUT → private S3/MinIO bucket
POST /api/direct-uploads/{id}/complete
  → HEAD validates size and checksum metadata
  → persisted video + queued ingestion job
worker download → independently recompute SHA-256 → FFmpeg processing
```

The second checksum verification prevents forged upload metadata from reaching inference. Media GET
URLs are short-lived signed URLs in S3 mode and ordinary `/media` paths in local mode.

`docker compose up --build` provisions PostgreSQL, MinIO, a private bucket with localhost CORS, the
API, and two workers. The MinIO API is on port 9000 and its console is on 9001. Development
credentials in Compose must never be reused outside local development.

The browser uses direct uploads when built with:

```env
REACT_APP_DIRECT_UPLOADS=true
```

In containers, set `S3_ENDPOINT_URL` to the internal service name and
`S3_PUBLIC_ENDPOINT_URL` to the browser-reachable origin. The hostname is part of the signature and
cannot be rewritten after a URL is signed.

Production requirements still include TLS, secret-manager credentials, bucket encryption,
least-privilege IAM, lifecycle rules for abandoned uploads/staging objects, and pinned container
image digests. The direct-upload API must also sit behind tenant authorization and per-user quotas;
presigned URLs protect bucket credentials, not application-level access.
