"""Pydantic schemas for normalized markets and extracted rules."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ExchangeName = Literal["polymarket", "kalshi"]


class NormalizedMarket(BaseModel):
    """Single shape consumed by every downstream agent."""

    model_config = ConfigDict(extra="ignore")

    exchange: ExchangeName
    external_id: str
    slug_or_ticker: str
    title: str
    description_raw: str = ""
    rules_raw: dict[str, Any] = Field(default_factory=dict)
    resolution_source: str | None = None
    expiration_ts: datetime | None = None
    status: str = "unknown"
    url: str | None = None

    def embedding_text(self) -> str:
        """Concatenated text used for similarity embedding."""
        parts = [self.title, self.description_raw]
        for v in self.rules_raw.values():
            if isinstance(v, str) and v.strip():
                parts.append(v)
        return "\n\n".join(p for p in parts if p)


class ExtractedRules(BaseModel):
    """Structured rule fields extracted from a market's free-form description."""

    model_config = ConfigDict(extra="ignore")

    resolution_source_primary: str = Field(
        default="",
        description="The primary data source the market settles on (e.g. 'AP race calls').",
    )
    resolution_source_fallback: str = Field(
        default="",
        description="Fallback or secondary source if the primary is unavailable.",
    )
    tiebreak_rule: str = Field(
        default="",
        description="How ties are resolved when the underlying value is exactly on the threshold.",
    )
    dead_heat_rule: str = Field(
        default="",
        description="How a 'dead heat' (no clear winner) is handled. Often subset of tiebreak.",
    )
    expiration_ts_utc: str = Field(
        default="",
        description="ISO 8601 UTC expiration timestamp as string. Empty if not specified.",
    )
    settlement_window: str = Field(
        default="",
        description="Time window between event end and market settlement.",
    )
    postponement_handling: str = Field(
        default="",
        description="How postponements, cancellations, or delays are treated.",
    )
    scope_summary: str = Field(
        default="",
        description="One-sentence summary of what exactly the market is asking.",
    )


class Candidate(BaseModel):
    """A cross-exchange similar market returned by the retriever."""

    market_id: str
    exchange: ExchangeName
    external_id: str
    title: str
    url: str | None = None
    similarity: float
    market: NormalizedMarket


class DimensionDiff(BaseModel):
    input: str = ""
    candidate: str = ""
    divergence: Literal["low", "medium", "high"] = "low"
    note: str = ""


class RiskRow(BaseModel):
    candidate: dict[str, Any]
    dimensions: dict[str, DimensionDiff]
    arbitrage_flag: Literal["potential", "none"] = "none"
    rationale: str = ""


class RiskMatrix(BaseModel):
    input: dict[str, Any]
    rows: list[RiskRow] = Field(default_factory=list)


class CompareRequest(BaseModel):
    url: str


class CompareCreated(BaseModel):
    comparison_id: str
    status: str


class CompareResult(BaseModel):
    comparison_id: str
    status: str
    risk_matrix: RiskMatrix | None = None
    error: str | None = None
