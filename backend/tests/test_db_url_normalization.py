from app.core.db import normalize_database_url


def test_sqlite_passthrough():
    url = "sqlite+aiosqlite:///./roofing.db"
    assert normalize_database_url(url) == url


def test_railway_style_postgres_url_gets_async_driver():
    url = "postgres://user:pass@containers-us-west-1.railway.app:5432/railway"
    result = normalize_database_url(url)
    assert result.startswith("postgresql+asyncpg://user:pass@containers-us-west-1.railway.app:5432/railway")


def test_postgresql_scheme_gets_async_driver():
    url = "postgresql://user:pass@localhost:5432/roofing"
    assert normalize_database_url(url).startswith("postgresql+asyncpg://user:pass@localhost:5432/roofing")


def test_sslmode_query_param_is_stripped():
    url = "postgres://user:pass@host:5432/db?sslmode=require"
    result = normalize_database_url(url)
    assert "sslmode" not in result
    assert result.startswith("postgresql+asyncpg://user:pass@host:5432/db")


def test_already_asyncpg_scheme_is_left_alone():
    url = "postgresql+asyncpg://user:pass@host:5432/db"
    assert normalize_database_url(url) == url
