"""Smoke tests for the Kalshi adapter."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.exchanges.kalshi import KalshiSource, _market_url


def test_parse_url_markets_path():
    ticker = KalshiSource.parse_url("https://kalshi.com/markets/PRESDEM2028")
    assert ticker == "PRESDEM2028"


def test_parse_url_events_path():
    ticker = KalshiSource.parse_url(
        "https://kalshi.com/events/PRES2028/PRESDEM2028"
    )
    assert ticker == "PRESDEM2028"


def test_market_url_drops_values_that_exceed_db_column() -> None:
    assert _market_url("A" * 2000) is None


@pytest.mark.asyncio
async def test_fetch_normalizes_market():
    sample = {
        "market": {
            "ticker": "PRESDEM2028",
            "title": "Will a Democrat win the 2028 presidential election?",
            "rules_primary": "Resolves YES if the Democratic nominee wins per AP race calls.",
            "rules_secondary": "Tiebreak: state-by-state electoral majority.",
            "expiration_time": "2028-11-08T00:00:00Z",
            "status": "open",
            "category": "Politics",
        }
    }
    with respx.mock(base_url="https://api.elections.kalshi.com/trade-api/v2") as r:
        r.get("/markets/PRESDEM2028").mock(return_value=httpx.Response(200, json=sample))
        source = KalshiSource()
        try:
            market = await source.fetch("PRESDEM2028")
        finally:
            await source.aclose()

    assert market.exchange == "kalshi"
    assert market.external_id == "PRESDEM2028"
    assert "AP race calls" in market.description_raw
    assert market.expiration_ts is not None
    assert market.status == "open"


@pytest.mark.asyncio
async def test_list_open_uses_events_and_expands_options():
    """`list_open` calls `/events?with_nested_markets=true` and emits one
    NormalizedMarket per nested contract, with the option name appended to the title
    when the parent event has multiple outcomes (so trigram search can match
    Polymarket-style "Will <X> be <Y>?" against the equivalent Kalshi contract)."""
    body = {
        "events": [
            {
                "event_ticker": "KXNEWPOPE-70",
                "series_ticker": "KXNEWPOPE",
                "title": "Who will the next Pope be?",
                "category": "Elections",
                "markets": [
                    {
                        "ticker": "KXNEWPOPE-70-PPIZ",
                        "title": "Who will the next Pope be?",
                        "yes_sub_title": "Pierbattista Pizzaballa",
                        "rules_primary": "Resolves YES if the named cardinal is elected Pope.",
                        "expiration_time": "2070-12-31T00:00:00Z",
                        "status": "active",
                    },
                    {
                        "ticker": "KXNEWPOPE-70-PPAR",
                        "title": "Who will the next Pope be?",
                        "yes_sub_title": "Pietro Parolin",
                        "rules_primary": "Resolves YES if the named cardinal is elected Pope.",
                        "expiration_time": "2070-12-31T00:00:00Z",
                        "status": "active",
                    },
                ],
            },
            {
                "event_ticker": "KXELONMARS-99",
                "series_ticker": "KXELONMARS",
                "title": "Will Elon Musk visit Mars in his lifetime?",
                "markets": [
                    {
                        "ticker": "KXELONMARS-99",
                        "title": "Will Elon Musk visit Mars before Aug 1, 2099?",
                        "yes_sub_title": "Mars",
                        "rules_primary": "Resolves YES on a confirmed crewed Mars landing.",
                        "expiration_time": "2099-08-01T00:00:00Z",
                        "status": "active",
                    }
                ],
            },
        ],
        "cursor": "next-page",
    }
    with respx.mock(base_url="https://api.elections.kalshi.com/trade-api/v2") as r:
        r.get("/events").mock(return_value=httpx.Response(200, json=body))
        source = KalshiSource()
        try:
            page = await source.list_open(limit=200)
        finally:
            await source.aclose()

    titles = [it.title for it in page.items]
    ids = [it.external_id for it in page.items]
    assert ids == ["KXNEWPOPE-70-PPIZ", "KXNEWPOPE-70-PPAR", "KXELONMARS-99"]
    # Multi-outcome event: option appended after em-dash.
    assert titles[0] == "Who will the next Pope be? \u2014 Pierbattista Pizzaballa"
    assert titles[1] == "Who will the next Pope be? \u2014 Pietro Parolin"
    # Single-outcome event: title left alone.
    assert titles[2] == "Will Elon Musk visit Mars in his lifetime?"
    assert page.next_cursor == "next-page"


@pytest.mark.asyncio
async def test_list_open_skips_mve_events():
    """MVE event groupings (auto-generated parlays) leak into `/events` too; their
    `series_ticker`/`event_ticker` carry the documented `KXMVE` prefix and must be
    skipped — but pagination must still keep the cursor alive so we reach real events."""
    body = {
        "events": [
            {
                "event_ticker": "KXMVECROSSCATEGORY-S2026-AAA",
                "series_ticker": "KXMVECROSSCATEGORY",
                "title": "auto-generated parlay",
                "markets": [
                    {
                        "ticker": "KXMVECROSSCATEGORY-S2026-AAA-LEG",
                        "title": "yes Leeds United,yes Delhi Capitals",
                        "status": "active",
                    }
                ],
            }
        ],
        "cursor": "cursor-2",
    }
    with respx.mock(base_url="https://api.elections.kalshi.com/trade-api/v2") as r:
        r.get("/events").mock(return_value=httpx.Response(200, json=body))
        source = KalshiSource()
        try:
            page = await source.list_open(limit=200)
        finally:
            await source.aclose()
    assert page.items == []
    assert page.next_cursor == "cursor-2"
