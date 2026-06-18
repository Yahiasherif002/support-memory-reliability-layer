"""Application settings.

Settings are read from the environment (prefix ``SMR_``) with sane defaults so
the app and the test-suite both run with zero configuration.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMR_", env_file=".env", extra="ignore")

    # SQLite by spec. Repositories isolate the dialect so Postgres is a localized swap.
    database_url: str = "sqlite:///./support_memory.db"
    sql_echo: bool = False

    # Default number of items the context builder will include before budgeting.
    default_context_budget: int = 12


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so settings are parsed once per process."""
    return Settings()
