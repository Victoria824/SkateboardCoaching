import logging
import signal
import time

from .config import settings
from .database import SessionLocal
from .service import claim_next_job, process_inference_job, process_job, process_sanitization_job


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
running = True


def stop_worker(*_) -> None:
    global running
    running = False


def run() -> None:
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    logger.info("Media worker started")
    while running:
        with SessionLocal() as session:
            job_id = claim_next_job(session)
            if job_id:
                from .models import ProcessingJob

                job = session.get(ProcessingJob, job_id)
                if job and job.job_type == "MODEL_INFERENCE":
                    process_inference_job(session, job_id)
                elif job and job.job_type == "PII_SANITIZATION":
                    process_sanitization_job(session, job_id)
                else:
                    process_job(session, job_id)
            else:
                time.sleep(settings.worker_poll_seconds)
    logger.info("Media worker stopped")


if __name__ == "__main__":
    run()
