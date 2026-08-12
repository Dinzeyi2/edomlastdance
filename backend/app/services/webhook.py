"""Optional push notification back to Lovable when a job finishes, so the UI
doesn't have to rely purely on polling GET /jobs/{id}. Signed with
WEBHOOK_SECRET (HMAC-SHA256) so Lovable's receiving endpoint can verify the
call actually came from this backend. Best-effort: a failed webhook does not
fail the job -- the job's result in Postgres is the source of truth, this is
just a faster notification path. Not exercised live from this sandbox (see
app/services/storage.py's note on network egress); implemented against
httpx's documented API.
"""
import hashlib
import hmac
import json
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def notify_lovable(job_id: str, user_id: str | None, status: str, result: dict | None) -> None:
    settings = get_settings()
    if not settings.lovable_webhook_url:
        return

    payload = {"job_id": job_id, "user_id": user_id, "status": status, "result": result}
    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(settings.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                settings.lovable_webhook_url,
                content=body,
                headers={"Content-Type": "application/json", "X-Webhook-Signature": signature},
            )
            resp.raise_for_status()
    except Exception:
        logger.exception("webhook to Lovable failed for job %s (job result is still saved)", job_id)
