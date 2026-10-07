from collections import Counter, defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import JobOutbox, ProcessingJob


router = APIRouter(prefix="/api/operations", tags=["operations"])


@router.get("/metrics")
def operation_metrics(session: Session = Depends(get_session)):
    jobs = list(session.scalars(select(ProcessingJob)).all())
    outbox = list(session.scalars(select(JobOutbox)).all())
    states = Counter(job.state for job in jobs)
    by_type = defaultdict(Counter)
    durations = defaultdict(list)
    queue_waits = defaultdict(list)
    for job in jobs:
        by_type[job.job_type][job.state] += 1
        if job.started_at and job.completed_at:
            durations[job.job_type].append(
                (job.completed_at - job.started_at).total_seconds() * 1000
            )
        if job.started_at:
            queue_waits[job.job_type].append(
                (job.started_at - job.created_at).total_seconds() * 1000
            )
    terminal = states["COMPLETED"] + states["FAILED"]
    return {
        "jobs_total": len(jobs),
        "states": dict(states),
        "by_type": {kind: dict(counts) for kind, counts in by_type.items()},
        "failure_rate": states["FAILED"] / terminal if terminal else 0,
        "average_duration_ms": {
            kind: sum(values) / len(values) for kind, values in durations.items() if values
        },
        "average_queue_wait_ms": {
            kind: sum(values) / len(values) for kind, values in queue_waits.items() if values
        },
        "leases": {
            "active": sum(
                job.lease_expires_at is not None and job.lease_expires_at >= datetime.utcnow()
                for job in jobs
            ),
            "expired": sum(
                job.lease_expires_at is not None and job.lease_expires_at < datetime.utcnow()
                for job in jobs
            ),
        },
        "outbox": dict(Counter(item.status for item in outbox)),
    }
