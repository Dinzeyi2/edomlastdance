"""Async SQLAlchemy engine/session setup. Deliberately backend-agnostic: no
PostGIS types anywhere, so this works unmodified against the default SQLite
file or a real Postgres URL. See app/pipeline/geo.py for how geo filtering is
done in application code instead of via a GIS extension.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
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
