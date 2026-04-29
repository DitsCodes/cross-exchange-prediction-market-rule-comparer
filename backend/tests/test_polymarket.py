"""Smoke tests for the Polymarket adapter using respx fixtures."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.exchanges.polymarket import PolymarketSource


def test_parse_url_market_path():
    slug = PolymarketSource.parse_url("https://polymarket.com/market/bitcoin-100k-2026")
    assert slug == "bitcoin-100k-2026"


def test_parse_url_event_path():
    slug = PolymarketSource.parse_url(
        "https://polymarket.com/event/2028-presidential-election/will-x-win"
    )
    assert slug == "will-x-win"


@pytest.mark.asyncio
async def test_fetch_normalizes_market():
    sample = {
        "id": "0x123",
        "conditionId": "0xCond",
        "slug": "bitcoin-100k-2026",
        "question": "Will Bitcoin reach $100k by end of 2026?",
        "description": "Resolves YES if BTC closes >= $100,000 on any day before 2026-12-31.",
        "resolutionSource": "Coinbase BTC-USD daily close",
        "endDate": "2026-12-31T23:59:59Z",
        "active": True,
        "closed": False,
    }
    with respx.mock(base_url="https://gamma-api.polymarket.com") as r:
        r.get("/markets/slug/bitcoin-100k-2026").mock(
            return_value=httpx.Response(200, json=sample)
        )
        source = PolymarketSource()
        try:
            market = await source.fetch("bitcoin-100k-2026")
        finally:
            await source.aclose()

    assert market.exchange == "polymarket"
    assert market.external_id == "0xCond"
    assert market.slug_or_ticker == "bitcoin-100k-2026"
    assert market.title.startswith("Will Bitcoin")
    assert market.resolution_source == "Coinbase BTC-USD daily close"
    assert market.expiration_ts is not None
    assert market.status == "open"
    assert market.url and "bitcoin-100k-2026" in market.url


@pytest.mark.asyncio
async def test_list_open_paginates():
    page1 = [
        {
            "id": str(i),
            "conditionId": f"0x{i}",
            "slug": f"market-{i}",
            "question": f"Question {i}?",
            "description": "desc",
            "active": True,
            "closed": False,
            "endDate": "2026-12-31T00:00:00Z",
        }
        for i in range(2)
    ]
    with respx.mock(base_url="https://gamma-api.polymarket.com") as r:
        r.get("/markets").mock(return_value=httpx.Response(200, json=page1))
        source = PolymarketSource()
        try:
            page = await source.list_open(limit=500)
        finally:
            await source.aclose()
    assert len(page.items) == 2
    assert page.next_cursor is None
