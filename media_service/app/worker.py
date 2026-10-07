import logging
import os
import signal
import socket
import time

from .config import settings
from .database import SessionLocal
from .service import claim_next_job, process_claimed_job


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
    worker_id = "{}-{}".format(socket.gethostname(), os.getpid())
    while running:
        with SessionLocal() as session:
            job_id = claim_next_job(session, worker_id=worker_id)
            if job_id:
                process_claimed_job(session, job_id)
            else:
                time.sleep(settings.worker_poll_seconds)
    logger.info("Media worker stopped")


if __name__ == "__main__":
    run()
