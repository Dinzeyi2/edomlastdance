"""Central config, env-driven. Mirrors the provider-factory pattern used
throughout this codebase: config picks a provider name, app/services/*.py
factories turn that into a concrete implementation. Nothing outside this file
and the factories should read os.environ directly.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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
    sam2_checkpoint_path: str = ""  # e.g. /models/sam2_hiera_large.pt -- see Dockerfile.worker
    # Confirmed by reading the actual build_sam.py source (its
    # HF_MODEL_ID_TO_FILENAMES table): the large model's config is at this
    # path *inside the installed package*, not a bare filename -- a
    # top-level "sam2_hiera_l.yaml" (no configs/ prefix) also exists in the
    # package but is the legacy/unused location. Matches
    # sam2_hiera_large.pt, the checkpoint your spec named.
    sam2_config_name: str = "configs/sam2/sam2_hiera_l.yaml"
    sam2_device: str = "cuda"  # "cuda" on a GPU worker, "cpu" otherwise (much slower)

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
