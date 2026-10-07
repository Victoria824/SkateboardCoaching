import os
import socket

from celery import Celery

from .config import settings
from .database import SessionLocal
from .service import claim_job_by_id, process_claimed_job


celery_app = Celery("snowboard-media", broker=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_soft_time_limit=1700,
    task_time_limit=1800,
)


@celery_app.task(name="media.process_job", bind=True, max_retries=0)
def process_job_task(self, job_id: str):
    worker_id = "celery:{}:{}".format(socket.gethostname(), os.getpid())
    with SessionLocal() as session:
        claimed = claim_job_by_id(session, job_id, worker_id)
        if claimed is None:
            return {"job_id": job_id, "status": "duplicate_or_not_claimable"}
        process_claimed_job(session, claimed)
        return {"job_id": job_id, "status": "processed"}
