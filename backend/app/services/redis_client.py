"""Shared async Redis client for the two uses your spec calls out beyond the
job queue: imagery tile caching (app/services/imagery_cache.py) and API rate
limiting (app/rate_limit.py). Uses redis.asyncio directly rather than going
through Celery, since these are plain cache/counter operations, not tasks.

Cached per-running-event-loop (not a single global singleton) rather than a
plain @lru_cache: an asyncio TCP connection is bound to the loop it was
opened on, so a naively cached client reused from a different loop breaks
with "attached to a different loop" -- this bit the test suite directly
(each test function gets its own event loop) and would just as easily bite
any other multi-loop context (e.g. a process that recreates its loop). A
WeakKeyDictionary keyed by the loop means each loop gets its own client and
stale entries for closed loops get garbage collected automatically.
"""
import asyncio
from weakref import WeakKeyDictionary

import redis.asyncio as redis

from app.config import get_settings

_clients: "WeakKeyDictionary[asyncio.AbstractEventLoop, redis.Redis]" = WeakKeyDictionary()


def get_redis() -> redis.Redis:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None:
        client = redis.from_url(get_settings().redis_url, decode_responses=False)
        _clients[loop] = client
    return client
