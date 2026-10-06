from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import ProcessingJob


router = APIRouter(prefix="/api/operations", tags=["operations"])


@router.get("/metrics")
def operation_metrics(session: Session = Depends(get_session)):
    jobs = list(session.scalars(select(ProcessingJob)).all())
    states = Counter(job.state for job in jobs)
    by_type = defaultdict(Counter)
    durations = defaultdict(list)
    for job in jobs:
        by_type[job.job_type][job.state] += 1
        if job.started_at and job.completed_at:
            durations[job.job_type].append(
                (job.completed_at - job.started_at).total_seconds() * 1000
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
    }
