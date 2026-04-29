"""Smoke tests for the Kalshi adapter."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.exchanges.kalshi import KalshiSource


def test_parse_url_markets_path():
    ticker = KalshiSource.parse_url("https://kalshi.com/markets/PRESDEM2028")
    assert ticker == "PRESDEM2028"


def test_parse_url_events_path():
    ticker = KalshiSource.parse_url(
        "https://kalshi.com/events/PRES2028/PRESDEM2028"
    )
    assert ticker == "PRESDEM2028"


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
async def test_list_open_with_cursor():
    body = {
        "markets": [
            {
                "ticker": "FOO-1",
                "title": "Foo 1",
                "rules_primary": "r",
                "expiration_time": "2026-12-31T00:00:00Z",
                "status": "open",
            }
        ],
        "cursor": "abc",
    }
    with respx.mock(base_url="https://api.elections.kalshi.com/trade-api/v2") as r:
        r.get("/markets").mock(return_value=httpx.Response(200, json=body))
        source = KalshiSource()
        try:
            page = await source.list_open(limit=200)
        finally:
            await source.aclose()
    assert len(page.items) == 1
    assert page.next_cursor == "abc"
