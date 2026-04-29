"""Shared LangGraph state for the compare workflow."""

from __future__ import annotations

from typing import TypedDict

from app.schemas.market import Candidate, ExtractedRules, NormalizedMarket, RiskRow


class CompareState(TypedDict, total=False):
    input_url: str
    input_market: NormalizedMarket | None
    input_market_id: str | None
    candidates: list[Candidate]
    extracted: dict[str, ExtractedRules]
    risk_matrix: list[RiskRow]
    errors: list[str]
    events: list[dict]


def new_state(url: str) -> CompareState:
    return CompareState(
        input_url=url,
        input_market=None,
        input_market_id=None,
        candidates=[],
        extracted={},
        risk_matrix=[],
        errors=[],
        events=[],
    )
