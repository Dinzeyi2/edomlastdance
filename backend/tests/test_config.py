"""Real bug this covers: a Railway env var value with a stray leading or
trailing space/newline -- easy to introduce via copy/paste, e.g. copying a
secret out of a chat message that had a trailing newline -- looks identical
in Railway's dashboard (values are masked) but fails an exact/constant-time
comparison in app/auth.py's `hmac.compare_digest(token, expected)`. Actually
happened: RAILWAY_API_KEY was set correctly-looking in Railway but every
request still got 401 until this got fixed.
"""
from app.config import Settings


def test_leading_and_trailing_whitespace_is_stripped_from_string_fields(monkeypatch):
    monkeypatch.setenv("RAILWAY_API_KEY", "  secret-value\n")
    monkeypatch.setenv("SAM2_MODAL_ENDPOINT_URL", "\thttps://example.modal.run ")

    settings = Settings()

    assert settings.railway_api_key == "secret-value"
    assert settings.sam2_modal_endpoint_url == "https://example.modal.run"


def test_values_without_whitespace_are_unaffected(monkeypatch):
    monkeypatch.setenv("RAILWAY_API_KEY", "clean-value")

    settings = Settings()

    assert settings.railway_api_key == "clean-value"


def test_non_string_fields_are_unaffected(monkeypatch):
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "45")

    settings = Settings()

    assert settings.celery_task_always_eager is True
    assert settings.rate_limit_per_minute == 45
