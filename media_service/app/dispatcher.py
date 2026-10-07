import logging
import time
from datetime import datetime
from typing import Callable

from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .models import JobOutbox, ProcessingJob


logger = logging.getLogger(__name__)


def publish_pending(session, publish: Callable[[str, str], None], limit: int = 100) -> int:
    stale = list(
        session.scalars(
            select(JobOutbox)
            .join(ProcessingJob, ProcessingJob.id == JobOutbox.job_id)
            .where(
                JobOutbox.status == "PENDING",
                ProcessingJob.state.notin_(("QUEUED", "RETRY_PENDING")),
            )
        ).all()
    )
    for item in stale:
        item.status = "SKIPPED"
        item.last_error = "Job is no longer dispatchable"
    if stale:
        session.commit()
    items = list(
        session.scalars(
            select(JobOutbox)
            .join(ProcessingJob, ProcessingJob.id == JobOutbox.job_id)
            .where(
                JobOutbox.status == "PENDING",
                ProcessingJob.state.in_(("QUEUED", "RETRY_PENDING")),
            )
            .order_by(JobOutbox.created_at)
            .limit(limit)
        ).all()
    )
    published = 0
    for item in items:
        try:
            publish(item.job_id, item.id)
            item.status = "PUBLISHED"
            item.published_at = datetime.utcnow()
            item.last_error = None
            published += 1
        except Exception as error:
            item.attempts += 1
            item.last_error = str(error)[-2000:]
            logger.exception("Outbox publish failed", extra={"outbox_id": item.id})
        session.commit()
    return published


def celery_publish(job_id: str, outbox_id: str) -> None:
    from .celery_tasks import celery_app

    celery_app.send_task("media.process_job", args=[job_id], task_id=outbox_id, queue="media")


def run() -> None:
    if settings.queue_backend != "celery":
        raise RuntimeError("Set MEDIA_QUEUE_BACKEND=celery to run the outbox dispatcher")
    logging.basicConfig(level=logging.INFO)
    while True:
        with SessionLocal() as session:
            published = publish_pending(session, celery_publish)
        if not published:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    run()
