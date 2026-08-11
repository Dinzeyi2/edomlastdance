"""Async SQLAlchemy engine/session setup. Deliberately backend-agnostic: no
PostGIS types anywhere, so this works unmodified against the default SQLite
file or a real Postgres URL. See app/pipeline/geo.py for how geo filtering is
done in application code instead of via a GIS extension.
"""
import asyncio
import logging
from collections.abc import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    """Railway (and most Postgres hosts) hand out a DATABASE_URL like
    `postgres://user:pass@host:port/db`, sometimes with a `sslmode=` query
    param -- that's the libpq/sync driver format. We need the asyncpg async
    driver, which uses a different scheme and doesn't understand `sslmode` as
    a URL param. This rewrites the scheme and drops that param; SQLite URLs
    pass through untouched.
    """
    if url.startswith("sqlite"):
        return url

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]

    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme == "postgresql":
        scheme = "postgresql+asyncpg"

    query_pairs = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() != "sslmode"]
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query_pairs), parts.fragment))


def make_engine(database_url: str | None = None):
    url = normalize_database_url(database_url or get_settings().database_url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_async_engine(url, connect_args=connect_args)


engine = make_engine()
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db(bind_engine=None) -> None:
    """Create all tables. Stands in for Alembic migrations in this v1 scaffold
    -- see README for the note on promoting this to real migrations."""
    target = bind_engine or engine
    async with target.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def init_db_with_retry(max_attempts: int = 10, base_delay_seconds: float = 1.0) -> None:
    """Same as init_db(), but retries with backoff. On a platform like Railway
    the web service and its Postgres addon can both be booting at once, so the
    DB may not accept connections yet on the first attempt -- without this the
    app would crash-loop instead of just waiting a few seconds.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            await init_db()
            return
        except Exception:
            if attempt == max_attempts:
                raise
            delay = base_delay_seconds * (2 ** (attempt - 1))
            logger.warning(
                "init_db failed (attempt %s/%s), retrying in %.1fs", attempt, max_attempts, delay
            )
            await asyncio.sleep(delay)
