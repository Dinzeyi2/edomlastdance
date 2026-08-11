"""Central configuration, env-driven. This is the one place that decides which
provider implementation (mock vs real) backs each external data source, so the
rest of the codebase never branches on config directly -- see
app/providers/__init__.py for the factory that reads these values.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./roofing.db"

    storm_provider: str = "mock"
    property_provider: str = "mock"
    imagery_provider: str = "mock"
    vision_provider: str = "stub"

    anthropic_api_key: str = ""
    anthropic_vision_model: str = "claude-sonnet-5"

    dev_seed_tenant_key: str = "dev-local-key"


@lru_cache
def get_settings() -> Settings:
    return Settings()
