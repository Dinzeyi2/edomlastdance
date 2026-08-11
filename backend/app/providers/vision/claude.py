"""Real damage-detection provider: sends the image to a Claude vision model
and asks for a structured damage assessment. Works against any image_ref that
is either a local file path (what the mock imagery provider returns) or an
http(s) URL (what a real imagery vendor would return) -- see _load_image.

Enable with VISION_PROVIDER=claude and ANTHROPIC_API_KEY set. This is the
integration path meant to prove out end-to-end even while imagery itself is
still mocked -- see backend/README.md for how to run it against the bundled
sample images.
"""
import base64
import json
import mimetypes
from pathlib import Path

import httpx
from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.providers.base import DamageAssessmentData, VisionProvider

SYSTEM_PROMPT = (
    "You are assisting a roofing sales team by triaging aerial roof imagery "
    "for likely storm damage. You will be shown a single top-down image of a "
    "roof, plus context about a recent storm event. Respond with STRICT JSON "
    "only, matching this shape, no prose outside the JSON:\n"
    '{"damage_confidence": <float 0.0-1.0>, "material_guess": <string or null>, '
    '"notes": <short string, 1-3 sentences, evidence a sales rep could cite '
    "when talking to the homeowner>}\n"
    "damage_confidence reflects how likely the roof shows hail/wind damage "
    "(missing/lifted shingles, granule loss, visible dents or debris) based on "
    "what is visible in the image. If the image gives no real signal, say so "
    "in notes and keep confidence low."
)


async def _load_image(image_ref: str) -> tuple[bytes, str]:
    if image_ref.startswith("http://") or image_ref.startswith("https://"):
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(image_ref)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/png").split(";")[0]
            return resp.content, content_type

    path = Path(image_ref)
    media_type = mimetypes.guess_type(path.name)[0] or "image/png"
    return path.read_bytes(), media_type


class ClaudeVisionProvider(VisionProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "VISION_PROVIDER=claude requires ANTHROPIC_API_KEY to be set."
            )
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_vision_model

    async def assess_damage(self, image_ref: str, context: dict) -> DamageAssessmentData:
        image_bytes, media_type = await _load_image(image_ref)
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        context_text = (
            f"Storm context: event_type={context.get('event_type')}, "
            f"max_hail_in={context.get('max_hail_in')}, "
            f"max_wind_mph={context.get('max_wind_mph')}, "
            f"roof_material_guess={context.get('roof_material_guess')}, "
            f"year_built={context.get('year_built')}."
        )

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                        },
                        {"type": "text", "text": context_text},
                    ],
                }
            ],
        )

        raw_text = "".join(block.text for block in response.content if block.type == "text")
        parsed = _parse_json_response(raw_text)

        return DamageAssessmentData(
            damage_confidence=max(0.0, min(1.0, float(parsed.get("damage_confidence", 0.0)))),
            material_guess=parsed.get("material_guess") or context.get("roof_material_guess"),
            notes=str(parsed.get("notes", raw_text))[:2000],
            provider="claude",
        )


def _parse_json_response(raw_text: str) -> dict:
    text = raw_text.strip()
    # Models sometimes wrap JSON in a code fence despite instructions -- strip it.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {"damage_confidence": 0.0, "material_guess": None, "notes": raw_text}
