"""Central config, env-driven. Mirrors the provider-factory pattern used
throughout this codebase: config picks a provider name, app/services/*.py
factories turn that into a concrete implementation. Nothing outside this file
and the factories should read os.environ directly.
"""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _strip_whitespace_from_string_fields(self) -> "Settings":
        """Real bug this fixed: a Railway env var value with a stray
        leading/trailing space or newline (easy to introduce via
        copy/paste -- e.g. copying a key out of a chat message that had a
        trailing newline) looks identical in Railway's dashboard but fails
        an exact/constant-time comparison in app/auth.py's
        `hmac.compare_digest(token, expected)`. Stripping every string
        field here means a whitespace-mangled secret in Railway's UI can't
        silently break auth or any other exact-match comparison.
        """
        for name, value in self.__dict__.items():
            if isinstance(value, str):
                stripped = value.strip()
                if stripped != value:
                    object.__setattr__(self, name, stripped)
        return self

    # --- auth (Lovable -> Railway) ---
    railway_api_key: str = "dev-local-key"

    # --- db / queue ---
    database_url: str = "sqlite:///./roofai.db"
    redis_url: str = "redis://localhost:6379/0"
    # Runs Celery tasks inline in the calling process instead of dispatching
    # to a worker over Redis. Useful for local dev/tests without a Redis
    # server running; Railway should NOT set this (real async workers).
    celery_task_always_eager: bool = False

    # --- providers ---
    imagery_provider: str = "mock"  # mock | google_solar | nearmap
    footprint_provider: str = "center_crop"  # center_crop | sam2 | osm
    defect_provider: str = "rule_based"  # rule_based | yolo
    llm_provider: str = "none"  # none | openai
    storage_provider: str = "local"  # local | s3

    # --- provider credentials (only read by the matching provider) ---
    google_solar_api_key: str = ""
    nearmap_api_key: str = ""
    openai_api_key: str = ""
    openai_reasoning_model: str = "gpt-4o-mini"
    yolo_model_path: str = ""
    # SAM-2 runs on Modal (Railway has no GPU tier), not in-process -- see
    # /modal-service and app/services/footprint.py's Sam2FootprintProvider,
    # which is an HTTP client, not a model loader.
    sam2_modal_endpoint_url: str = ""
    sam2_modal_api_key: str = ""

    # --- storage ---
    s3_endpoint: str = ""  # e.g. https://<accountid>.r2.cloudflarestorage.com for R2; blank = AWS S3
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "roofai"
    s3_region: str = "auto"
    local_storage_dir: str = "./storage"

    # --- webhook back to Lovable ---
    lovable_webhook_url: str = ""
    webhook_secret: str = "dev-webhook-secret"

    # --- rate limiting (Redis-backed, applied to /analyze*) ---
    # 0 disables it. Fixed-window per bearer token -- see app/rate_limit.py.
    rate_limit_per_minute: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
