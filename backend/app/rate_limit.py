"""Redis-backed rate limiting -- the other Redis use your spec called out
beyond the job queue. Fixed-window counter per bearer token (there's one
shared token in this single-caller model, so this effectively caps total
request volume from your Lovable app -- protects against a runaway loop
racking up imagery/LLM costs). Applied to the expensive endpoints
(/analyze, /analyze/async) via a FastAPI dependency, ordered after
require_api_key so an unauthenticated request gets 401, not 429.

Fails OPEN if Redis itself is unreachable: a cache/rate-limit layer being
down should degrade gracefully, not take the whole API down with it (and
concretely, without this, every local-dev/test run would need a Redis
server just to hit /analyze at all, which defeats the "zero infra" local
setup documented in the README). This was caught by actually testing the
no-Redis case, not assumed -- see the git history.
"""
import logging
import time

from fastapi import Header, HTTPException, status

from app.config import get_settings

logger = logging.getLogger(__name__)


async def enforce_rate_limit(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.rate_limit_per_minute <= 0:
        return  # disabled

    from app.services.redis_client import get_redis  # lazy: no Redis dependency when disabled

    token = authorization[len("Bearer ") :] if authorization and authorization.startswith("Bearer ") else "anonymous"
    window = int(time.time() // 60)
    key = f"ratelimit:{token}:{window}"

    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
    except Exception:
        logger.warning("rate limiter: Redis unreachable, failing open for this request", exc_info=True)
        return

    if count > settings.rate_limit_per_minute:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Rate limit exceeded: {settings.rate_limit_per_minute} requests/minute.",
        )
