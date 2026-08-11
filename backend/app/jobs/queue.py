"""Thin helpers around the `jobs` table -- enqueue, and claim-one-pending
with SELECT ... FOR UPDATE SKIP LOCKED so multiple worker processes can run
safely against Postgres. SQLite doesn't support SKIP LOCKED or real
concurrent writers, which is fine for local dev/tests (single worker), but is
the reason this whole layer is a clean swap point for a real broker
(Celery/arq+Redis) if concurrent workers are ever needed against SQLite.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job


async def enqueue(db: AsyncSession, job_type: str, payload: dict) -> Job:
    job = Job(job_type=job_type, payload=payload, status="pending")
    db.add(job)
    await db.flush()
    return job


async def claim_next(db: AsyncSession) -> Job | None:
    stmt = select(Job).where(Job.status == "pending").order_by(Job.created_at).limit(1)
    if db.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update(skip_locked=True)
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None
    job.status = "running"
    job.attempts += 1
    await db.flush()
    return job
