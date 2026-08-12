"""Redis-backed tile cache -- your spec's "cache downloaded tiles so you
don't re-download every time." Wraps whichever ImageryProvider is configured
(mock or a real vendor) so this is a transparent layer, not something each
provider has to implement itself.

Historical (compare_year) imagery is cached with a long TTL since a given
year's capture never changes once it exists. "Current" imagery (no year) uses
a much shorter TTL since a real vendor's "most recent" capture can be
refreshed.

Fails OPEN if Redis is unreachable: falls straight through to the
underlying provider rather than failing the whole request (same reasoning
as app/rate_limit.py -- a cache being down shouldn't take the primary
imagery fetch down with it, and this keeps local dev/tests working without
requiring a Redis server just to hit /analyze).
"""
import base64
import json
import logging
from datetime import date

from app.services.imagery import ImageryProvider, ImageryResult

logger = logging.getLogger(__name__)

CURRENT_TTL_SECONDS = 6 * 60 * 60  # 6 hours
HISTORICAL_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


def _cache_key(provider_name: str, lat: float, lng: float, resolution_cm: int, year: int | None) -> str:
    return f"imagery:{provider_name}:{round(lat, 5)}:{round(lng, 5)}:{resolution_cm}:{year or 'current'}"


class CachedImageryProvider(ImageryProvider):
    def __init__(self, inner: ImageryProvider, provider_name: str):
        self._inner = inner
        self._provider_name = provider_name

    async def fetch_image(
        self, lat: float, lng: float, resolution_cm: int, year: int | None = None
    ) -> ImageryResult:
        from app.services.redis_client import get_redis  # lazy: avoids a Redis dependency at import time for callers that never hit this path

        key = _cache_key(self._provider_name, lat, lng, resolution_cm, year)

        try:
            redis = get_redis()
            cached = await redis.get(key)
        except Exception:
            logger.warning("imagery cache: Redis unreachable, skipping cache for this request", exc_info=True)
            return await self._inner.fetch_image(lat, lng, resolution_cm, year)

        if cached is not None:
            payload = json.loads(cached)
            return ImageryResult(
                image_bytes=base64.b64decode(payload["image_b64"]),
                media_type=payload["media_type"],
                captured_date=date.fromisoformat(payload["captured_date"]) if payload["captured_date"] else None,
                provider=payload["provider"] + "_cached",
            )

        result = await self._inner.fetch_image(lat, lng, resolution_cm, year)
        payload = {
            "image_b64": base64.b64encode(result.image_bytes).decode("ascii"),
            "media_type": result.media_type,
            "captured_date": result.captured_date.isoformat() if result.captured_date else None,
            "provider": result.provider,
        }
        ttl = HISTORICAL_TTL_SECONDS if year else CURRENT_TTL_SECONDS
        try:
            await redis.set(key, json.dumps(payload), ex=ttl)
        except Exception:
            logger.warning("imagery cache: failed to write to Redis, continuing without caching", exc_info=True)
        return result
