"""Single shared-secret auth: Lovable is the only caller of this API, so
there's one bearer token (RAILWAY_API_KEY), not per-tenant accounts. Compared
with constant-time to avoid a timing side-channel on the comparison.
"""
import hmac

from fastapi import Header, HTTPException, status

from app.config import get_settings


async def require_api_key(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Bearer token")
    token = authorization[len("Bearer ") :]
    expected = get_settings().railway_api_key
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
