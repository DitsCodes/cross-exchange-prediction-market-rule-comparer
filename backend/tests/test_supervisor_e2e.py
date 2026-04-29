"""End-to-end supervisor test: real exchange API + mocked DB/embeddings."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.agents import market_fetcher, similarity_retriever
from app.agents.state import new_state
from app.agents.supervisor import build_graph
from app.schemas.market import Candidate, NormalizedMarket


def _fake_kalshi_candidate() -> Candidate:
    market = NormalizedMarket(
        exchange="kalshi",
        external_id="KXMARSCANDIDATE",
        slug_or_ticker="KXMARSCANDIDATE",
        title="Will a human reach Mars before 2050?",
        description_raw=(
            "If a human-crewed spacecraft lands on the Martian surface and the crew "
            "disembarks before Jan 1, 2050, the market resolves YES per NASA confirmation. "
            "Tiebreak: dead heat resolves NO."
        ),
        rules_raw={
            "rules_primary": "If a human-crewed spacecraft lands on the Martian surface...",
        },
        resolution_source="NASA confirmation",
        expiration_ts=datetime(2050, 1, 1, tzinfo=timezone.utc),
        status="open",
        url="https://kalshi.com/markets/KXMARSCANDIDATE",
    )
    return Candidate(
        market_id="11111111-1111-1111-1111-111111111111",
        exchange="kalshi",
        external_id=market.external_id,
        title=market.title,
        url=market.url,
        similarity=0.78,
        market=market,
    )


@pytest.mark.asyncio
async def test_supervisor_runs_against_live_polymarket(monkeypatch):
    """Drive the compiled LangGraph against a live Polymarket URL, with DB/embeddings mocked."""
    sample = {
        "id": "12345",
        "conditionId": "0xCondAbc",
        "slug": "human-mars-2050",
        "question": "Will a human reach Mars before 2050?",
        "description": (
            "Resolves YES if a human-crewed spacecraft lands on Mars before "
            "January 1 2050 per NASA confirmation. Dead-heat resolves NO."
        ),
        "resolutionSource": "NASA",
        "endDate": "2050-01-01T00:00:00Z",
        "active": True,
        "closed": False,
        "outcomes": '["Yes", "No"]',
    }

    monkeypatch.setattr(market_fetcher, "_upsert_input_market", lambda mkt: "abc")

    async def _fake_retriever(state):
        evts = state.get("events", [])
        evts.append({"step": "retriever", "status": "ok", "candidates": 1})
        return {**state, "candidates": [_fake_kalshi_candidate()], "events": evts}

    monkeypatch.setattr(
        similarity_retriever, "similarity_retriever_node", _fake_retriever
    )

    from app.agents import supervisor as sup_module
    sup_module._compiled = None
    sup_module.similarity_retriever_node = _fake_retriever

    graph = build_graph()
    initial = new_state("https://polymarket.com/market/human-mars-2050")

    with respx.mock(base_url="https://gamma-api.polymarket.com") as r:
        r.get("/markets/slug/human-mars-2050").mock(
            return_value=httpx.Response(200, json=sample)
        )
        final = await graph.ainvoke(initial)

    assert final.get("input_market") is not None, final.get("errors")
    assert final["input_market"].title.startswith("Will a human")
    assert final["candidates"], "retriever should have produced a candidate"
    assert final["risk_matrix"], "synthesizer should have produced rows"

    row = final["risk_matrix"][0]
    assert set(row.dimensions.keys()) == {"resolution_source", "tiebreak", "expiration", "scope"}
    assert row.arbitrage_flag in {"potential", "none"}
    assert row.candidate["exchange"] == "kalshi"

    steps = [e["step"] for e in final.get("events", []) if "step" in e]
    assert "fetcher" in steps
    assert "retriever" in steps
    assert "extractor" in steps
    assert "synthesizer" in steps
