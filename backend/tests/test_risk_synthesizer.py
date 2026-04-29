"""Test the deterministic per-dimension diff scorer in isolation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.agents.risk_synthesizer import (
    _diff_expiration,
    _diff_resolution_source,
    _diff_scope,
    _diff_tiebreak,
    _format_gap,
    _heuristic_rationale,
    risk_synthesizer_node,
)
from app.schemas.market import (
    Candidate,
    DimensionDiff,
    ExtractedRules,
    NormalizedMarket,
)


def _market(title: str, expiration: datetime | None = None, exchange: str = "polymarket") -> NormalizedMarket:
    return NormalizedMarket(
        exchange=exchange,
        external_id=title.lower().replace(" ", "-"),
        slug_or_ticker=title.lower().replace(" ", "-"),
        title=title,
        expiration_ts=expiration,
        status="open",
    )


def test_resolution_source_aligned_when_identical():
    a = ExtractedRules(resolution_source_primary="AP race calls")
    b = ExtractedRules(resolution_source_primary="AP race calls")
    diff = _diff_resolution_source(a, b)
    assert diff.divergence == "low"


def test_resolution_source_high_when_different():
    a = ExtractedRules(resolution_source_primary="Decision Desk HQ")
    b = ExtractedRules(resolution_source_primary="Edison Research")
    diff = _diff_resolution_source(a, b)
    assert diff.divergence == "high"


def test_tiebreak_classification_high():
    a = ExtractedRules(tiebreak_rule="First to cross 50% wins.")
    b = ExtractedRules(tiebreak_rule="Pro rata payout among ties.")
    diff = _diff_tiebreak(a, b)
    assert diff.divergence == "high"


def test_expiration_high_when_far_apart():
    now = datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)
    a = _market("X", expiration=now)
    b = _market("X", expiration=now + timedelta(hours=72), exchange="kalshi")
    diff = _diff_expiration(a, b, ExtractedRules(), ExtractedRules())
    assert diff.divergence == "high"


def test_expiration_low_when_within_hour():
    now = datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)
    a = _market("X", expiration=now)
    b = _market("X", expiration=now + timedelta(minutes=30), exchange="kalshi")
    diff = _diff_expiration(a, b, ExtractedRules(), ExtractedRules())
    assert diff.divergence == "low"


def test_format_gap_picks_sensible_units():
    assert _format_gap(45) == "45s"
    assert _format_gap(3600 * 2) == "2.0h"
    assert _format_gap(3600 * 24 * 5) == "5.0d"
    assert _format_gap(3600 * 24 * 90) == "3.0mo"
    assert _format_gap(3600 * 24 * 365 * 5) == "5.0y"


def test_expiration_huge_gap_renders_in_years():
    """Regression test: 72-year gap must not be rendered as a 6-digit hour count."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = _market("X", expiration=now)
    b = _market("X", expiration=now.replace(year=2099), exchange="kalshi")
    diff = _diff_expiration(a, b, ExtractedRules(), ExtractedRules())
    assert diff.divergence == "high"
    assert "y gap" in diff.note  # rendered as years, not hours


def test_scope_low_when_overlapping():
    a = ExtractedRules(scope_summary="Will Bitcoin reach 100,000 dollars by end of 2026")
    b = ExtractedRules(scope_summary="Will Bitcoin reach 100000 dollars before 2026 ends")
    diff = _diff_scope(a, b)
    assert diff.divergence in {"low", "medium"}


def test_heuristic_rationale_flags_potential_when_high():
    dims = {
        "resolution_source": DimensionDiff(divergence="high", note="different sources"),
        "tiebreak": DimensionDiff(divergence="low", note="ok"),
        "expiration": DimensionDiff(divergence="low", note="ok"),
        "scope": DimensionDiff(divergence="low", note="ok"),
    }
    flag, rationale = _heuristic_rationale(dims)
    assert flag == "potential"
    assert "resolution_source" in rationale or "High divergence" in rationale


def test_heuristic_rationale_flags_none_when_aligned():
    dims = {
        "resolution_source": DimensionDiff(divergence="low", note=""),
        "tiebreak": DimensionDiff(divergence="low", note=""),
        "expiration": DimensionDiff(divergence="low", note=""),
        "scope": DimensionDiff(divergence="low", note=""),
    }
    flag, _ = _heuristic_rationale(dims)
    assert flag == "none"


def test_synthesizer_node_runs_without_llm(monkeypatch):
    """End-to-end node test: heuristic mode (no ANTHROPIC_API_KEY)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    input_market = _market("Will Bitcoin reach 100k", expiration=now)
    cand_market = _market("BTC over 100k by 2026", expiration=now + timedelta(hours=48), exchange="kalshi")
    candidate = Candidate(
        market_id="11111111-1111-1111-1111-111111111111",
        exchange="kalshi",
        external_id="BTC-100K-2026",
        title=cand_market.title,
        url=None,
        similarity=0.85,
        market=cand_market,
    )

    state = {
        "input_url": "https://polymarket.com/market/bitcoin-100k-2026",
        "input_market": input_market,
        "candidates": [candidate],
        "extracted": {
            "input": ExtractedRules(
                resolution_source_primary="Coinbase BTC-USD daily close",
                tiebreak_rule="First daily close above 100k wins",
                scope_summary="BTC reaches 100k by end of 2026",
            ),
            candidate.market_id: ExtractedRules(
                resolution_source_primary="CME BTC futures settlement",
                tiebreak_rule="Pro-rata across all ties",
                scope_summary="BTC over 100k by 2026",
            ),
        },
        "events": [],
    }

    result = asyncio.run(risk_synthesizer_node(state))
    rows = result["risk_matrix"]
    assert len(rows) == 1
    assert set(rows[0].dimensions.keys()) == {"resolution_source", "tiebreak", "expiration", "scope"}
    assert rows[0].arbitrage_flag in {"potential", "none"}
