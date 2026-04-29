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
        description="SQLAlchemy connection string. Must be a Postgres instance with the vector extension available.",
    )

    anthropic_api_key: str = Field(default="", description="Required for the LangGraph supervisor.")
    anthropic_model: str = Field(default="claude-sonnet-4-5")

    voyage_api_key: str = Field(default="", description="Required for embeddings.")
    voyage_model: str = Field(default="voyage-3-large")
    voyage_dim: int = Field(default=1024)

    polymarket_base: AnyHttpUrl = Field(default="https://gamma-api.polymarket.com")
    kalshi_base: AnyHttpUrl = Field(default="https://api.elections.kalshi.com/trade-api/v2")

    ingest_interval_minutes: int = Field(default=30)
    ingest_on_startup: bool = Field(default=False)
    ingest_polymarket_page_size: int = Field(default=500)
    ingest_kalshi_page_size: int = Field(default=200)
    ingest_max_pages: int = Field(default=20)

    similarity_top_k: int = Field(default=8)
    similarity_min_score: float = Field(default=0.72)

    admin_token: str = Field(default="change-me")
    cors_origins: str = Field(default="http://localhost:3000")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
