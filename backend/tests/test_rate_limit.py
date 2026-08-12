"""Proves the rate limiter actually enforces a limit against the real Redis
server started in conftest.py -- not just that the code imports. Calls
enforce_rate_limit() directly rather than through the HTTP client: it's a
distinct concern from auth (require_api_key checks the token is *valid*;
this only cares about *how many* requests a given token string has made),
and unit-testing it directly lets these tests use arbitrary token strings to
prove per-token isolation without needing multiple real API keys configured.
The full dependency chain (auth -> rate limit, in that order) is exercised
by tests/test_api.py.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.rate_limit import enforce_rate_limit


def _settings(limit: int) -> SimpleNamespace:
    return SimpleNamespace(rate_limit_per_minute=limit)


async def test_rate_limit_enforced_for_real(monkeypatch):
    monkeypatch.setattr("app.rate_limit.get_settings", lambda: _settings(2))

    await enforce_rate_limit(authorization="Bearer enforced-test-token")
    await enforce_rate_limit(authorization="Bearer enforced-test-token")
    with pytest.raises(HTTPException) as exc_info:
        await enforce_rate_limit(authorization="Bearer enforced-test-token")
    assert exc_info.value.status_code == 429


async def test_rate_limit_is_per_token(monkeypatch):
    monkeypatch.setattr("app.rate_limit.get_settings", lambda: _settings(1))

    await enforce_rate_limit(authorization="Bearer token-a")
    # A different token gets its own budget -- not limited by token-a's usage.
    await enforce_rate_limit(authorization="Bearer token-b")

    with pytest.raises(HTTPException):
        await enforce_rate_limit(authorization="Bearer token-a")


async def test_rate_limit_disabled_when_zero(monkeypatch):
    monkeypatch.setattr("app.rate_limit.get_settings", lambda: _settings(0))

    for _ in range(10):
        await enforce_rate_limit(authorization="Bearer disabled-limit-token")  # never raises


async def test_fails_open_when_redis_is_unreachable(monkeypatch):
    """Caught by actually testing this: without this, the whole API would
    500 on every /analyze call whenever Redis is down -- a cache/rate-limit
    layer being unavailable should degrade gracefully, not take the primary
    request down with it. Points get_redis at a port nothing is listening
    on to force a real connection failure, not a mocked one."""
    import redis.asyncio as redis_asyncio

    monkeypatch.setattr("app.rate_limit.get_settings", lambda: _settings(1))
    monkeypatch.setattr(
        "app.services.redis_client.get_redis",
        lambda: redis_asyncio.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=1),
    )

    # Would raise 429 on the 2nd call if Redis were reachable (limit=1) --
    # instead every call should succeed since it fails open.
    await enforce_rate_limit(authorization="Bearer redis-down-token")
    await enforce_rate_limit(authorization="Bearer redis-down-token")
