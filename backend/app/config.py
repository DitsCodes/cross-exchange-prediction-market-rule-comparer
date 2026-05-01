"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "rulec"
    environment: str = Field(default="dev")
    log_level: str = Field(default="INFO")

    database_url: str = Field(
        default="postgresql+psycopg://rulec:rulec@localhost:5432/rulec",
        description="SQLAlchemy connection string. Plain Postgres is enough; the pg_trgm extension is enabled by migration.",
    )

    anthropic_api_key: str = Field(default="", description="Required for the LangGraph supervisor.")
    anthropic_model: str = Field(default="claude-sonnet-4-5")

    polymarket_base: AnyHttpUrl = Field(default="https://gamma-api.polymarket.com")
    kalshi_base: AnyHttpUrl = Field(default="https://api.elections.kalshi.com/trade-api/v2")

    ingest_interval_minutes: int = Field(default=30)
    ingest_on_startup: bool = Field(default=False)
    ingest_polymarket_page_size: int = Field(default=500)
    ingest_kalshi_page_size: int = Field(default=200)
    ingest_max_pages: int = Field(default=20)

    similarity_top_k: int = Field(default=8)
    similarity_min_score: float = Field(
        default=0.18,
        description=(
            "Min pg_trgm similarity (0..1) for cross-exchange neighbors. "
            "Trigram scores run lower than cosine; 0.18 is a pragmatic default."
        ),
    )

    admin_token: str = Field(default="change-me")
    cors_origins: str = Field(default="http://localhost:3000")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
