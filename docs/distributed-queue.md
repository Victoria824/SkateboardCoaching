# Redis/Celery distributed job delivery

PostgreSQL remains the authoritative record for job state. A `processing_jobs` row and its
`job_outbox` event are created in the same database transaction. The dispatcher publishes pending
events to Redis/Celery and marks them published only after the broker accepts them.

```text
API transaction → processing_jobs + job_outbox
                            ↓
                    outbox dispatcher
                            ↓
                       Redis broker
                            ↓
                Celery media workers × N
                            ↓
       compare-and-swap claim + PostgreSQL lease
```

Delivery is intentionally at least once. Each Celery message carries the outbox ID as its task ID,
and the worker must atomically claim the named job before doing work. Duplicate messages return
without processing. Workers use late acknowledgement, reject-on-worker-loss, prefetch 1, hard and
soft time limits, and one process per media worker in Compose.

Leases contain worker ID, heartbeat, and expiry. Inference renews its lease while each frame's
outputs are persisted; ingestion renews between stages. The initial lease and Celery hard limit are
both 30 minutes, so a lost process becomes reclaimable rather than overlapping a still-valid task.
An expired lease can be reclaimed until `max_attempts`; an exhausted job is marked
`WORKER_LEASE_EXPIRED`. This same mechanism protects the local database polling worker when
`MEDIA_QUEUE_BACKEND=database`.

Operational metrics expose queue wait, execution duration, active/expired leases, failures, and
outbox backlog. Remaining hardening includes a dispatcher claim/lease for multiple dispatchers,
broker authentication/TLS, Redis Sentinel or managed Redis, and a dead-letter administration UI.
