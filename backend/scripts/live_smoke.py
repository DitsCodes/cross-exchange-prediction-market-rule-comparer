"""LIVE end-to-end smoke against real Polymarket API.

This is NOT a pytest — it makes real HTTP calls. Run manually with:
    PYTHONPATH=. python scripts/live_smoke.py [<polymarket-or-kalshi-url>]

Mocks out the DB persistence and similarity retriever (since neither needs to
actually run for a smoke test), but every other layer is real:
- live exchange API call from the MarketFetcher node
- heuristic rules extraction (no LLM needed)
- deterministic per-dimension diff scoring + heuristic rationale
"""

import asyncio
import json
import sys
from datetime import datetime, timezone

from app.agents import market_fetcher, supervisor
from app.agents.state import new_state
from app.schemas.market import Candidate, NormalizedMarket


def _fake_db_upsert(market) -> str:
    return "00000000-0000-0000-0000-000000000000"


def _fake_kalshi_candidate(input_title: str) -> Candidate:
    """A hand-crafted candidate that we pretend the vector retriever found."""
    market = NormalizedMarket(
        exchange="kalshi",
        external_id="KXFAKEKALSHI",
        slug_or_ticker="KXFAKEKALSHI",
        title=f"Kalshi version: {input_title}",
        description_raw=(
            "If the underlying event occurs before its stated deadline per the "
            "official source, the market resolves YES. Tiebreak: pro-rata payout."
        ),
        rules_raw={"rules_primary": "Pro-rata tiebreak."},
        resolution_source="Official broadcaster confirmation",
        expiration_ts=datetime(2099, 1, 1, tzinfo=timezone.utc),
        status="open",
    )
    return Candidate(
        market_id="11111111-1111-1111-1111-111111111111",
        exchange="kalshi",
        external_id="KXFAKEKALSHI",
        title=market.title,
        url=None,
        similarity=0.81,
        market=market,
    )


async def main(url: str) -> None:
    # Patch the DB persistence and similarity retriever so the graph can run end-to-end
    # against the real exchange API.
    market_fetcher._upsert_input_market = _fake_db_upsert  # type: ignore[assignment]

    async def _fake_retriever(state):
        evts = state.get("events", [])
        market = state.get("input_market")
        title = market.title if market else "?"
        evts.append({"step": "retriever", "status": "ok", "candidates": 1})
        return {**state, "candidates": [_fake_kalshi_candidate(title)], "events": evts}

    supervisor._compiled = None
    supervisor.similarity_retriever_node = _fake_retriever

    graph = supervisor.build_graph()
    final = await graph.ainvoke(new_state(url))
    payload = supervisor.build_risk_matrix_payload(final)
    payload["errors"] = final.get("errors", [])
    payload["events"] = [e for e in final.get("events", [])]

    print("=" * 60)
    print("LIVE E2E result for", url)
    print("=" * 60)
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    target = sys.argv[1] if len(sys.argv) > 1 else (
        "https://polymarket.com/market/russia-ukraine-ceasefire-before-gta-vi-554"
    )
    asyncio.run(main(target))
