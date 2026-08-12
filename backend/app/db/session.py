"""Two DB stacks share one DATABASE_URL:
  - an ASYNC engine/session for the FastAPI process (asyncpg driver)
  - a SYNC engine/session for the Celery worker process (psycopg2 driver;
    Celery tasks are plain synchronous functions, so there's no point paying
    for an event loop inside a worker whose only job is to run one task at a
    time)

Both normalize whatever DATABASE_URL is supplied (Railway hands out
`postgres://...`, the sync/libpq scheme) to the right driver scheme. SQLite
passes through unchanged and works for both stacks, which is what local
dev/tests use by default -- no Postgres required to run this locally.
"""
from collections.abc import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_async_database_url(url: str) -> str:
    """asyncpg driver scheme; asyncpg also doesn't understand `sslmode` as a
    URL query param the way libpq-based drivers do, so it's stripped."""
    if url.startswith("sqlite"):
        return "sqlite+aiosqlite" + url[len("sqlite") :]

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    parts = urlsplit(url)
    scheme = "postgresql+asyncpg" if parts.scheme == "postgresql" else parts.scheme
    query_pairs = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() != "sslmode"]
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query_pairs), parts.fragment))


def normalize_sync_database_url(url: str) -> str:
    """psycopg2 driver scheme; psycopg2 understands `sslmode` natively so it's
    left alone."""
    if url.startswith("sqlite"):
        return url  # plain `sqlite:///...` is already the sync form

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    parts = urlsplit(url)
    scheme = "postgresql+psycopg2" if parts.scheme == "postgresql" else parts.scheme
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def make_async_engine(database_url: str | None = None):
    url = normalize_async_database_url(database_url or get_settings().database_url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_async_engine(url, connect_args=connect_args)


def make_sync_engine(database_url: str | None = None):
    url = normalize_sync_database_url(database_url or get_settings().database_url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


async_engine = make_async_engine()
AsyncSessionLocal = async_sessionmaker(bind=async_engine, expire_on_commit=False, class_=AsyncSession)

sync_engine = make_sync_engine()
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db_async(max_attempts: int = 10, base_delay_seconds: float = 1.0) -> None:
    """Create all tables, retrying with backoff -- on Railway the web service
    and its Postgres addon can both be booting at once."""
    import asyncio
    import logging

    logger = logging.getLogger(__name__)
    for attempt in range(1, max_attempts + 1):
        try:
            async with async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception:
            if attempt == max_attempts:
                raise
            delay = base_delay_seconds * (2 ** (attempt - 1))
            logger.warning("init_db failed (attempt %s/%s), retrying in %.1fs", attempt, max_attempts, delay)
            await asyncio.sleep(delay)
