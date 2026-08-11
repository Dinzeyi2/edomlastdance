"""Standalone worker process: `python -m app.jobs.worker`. Polls the jobs
table and drains it in a loop. Not required for the demo flow (the ingest API
route drains synchronously, see app/jobs/runner.py) but this is what a real
deployment would run continuously so ingestion, imagery fetch, inference, and
scoring happen off the request path.
"""
import asyncio
import logging

from app.core.db import SessionLocal, init_db
from app.jobs.runner import drain

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 2


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await init_db()
    logger.info("worker started, polling every %ss", POLL_INTERVAL_SECONDS)
    while True:
        async with SessionLocal() as db:
            processed = await drain(db)
        if processed:
            logger.info("processed %s job(s)", processed)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
