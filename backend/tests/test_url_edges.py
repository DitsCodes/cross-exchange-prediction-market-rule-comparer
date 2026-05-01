"""URL parser edge-case tests."""

from __future__ import annotations

import pytest

from app.exchanges import detect_exchange
from app.exchanges.base import UnsupportedURLError
from app.exchanges.kalshi import KalshiSource
from app.exchanges.polymarket import PolymarketSource


@pytest.mark.parametrize(
    "url, slug",
    [
        ("https://polymarket.com/market/foo-bar-2026", "foo-bar-2026"),
        ("https://polymarket.com/market/foo-bar-2026/", "foo-bar-2026"),
        ("https://polymarket.com/market/foo-bar-2026?utm_source=x", "foo-bar-2026"),
        ("https://www.polymarket.com/market/foo-bar-2026", "foo-bar-2026"),
        ("https://polymarket.com/event/election-2028/will-x-win", "will-x-win"),
        ("https://polymarket.com/event/election-2028", "election-2028"),
        ("https://polymarket.com/event/election-2028/will-x-win?tid=abc#anchor", "will-x-win"),
        ("https://polymarket.com/markets/foo-bar-2026", "foo-bar-2026"),
        ("https://www.polymarket.com/markets/foo-bar-2026", "foo-bar-2026"),
    ],
)
def test_polymarket_url_shapes(url: str, slug: str):
    assert PolymarketSource.parse_url(url) == slug


@pytest.mark.parametrize(
    "url, ticker",
    [
        ("https://kalshi.com/markets/PRESDEM2028", "PRESDEM2028"),
        ("https://kalshi.com/markets/presdem2028", "PRESDEM2028"),
        ("https://kalshi.com/markets/PRESDEM2028/", "PRESDEM2028"),
        ("https://kalshi.com/markets/PRESDEM2028?ref=hn", "PRESDEM2028"),
        ("https://www.kalshi.com/markets/PRESDEM2028", "PRESDEM2028"),
        ("https://kalshi.com/events/PRES2028/PRESDEM2028", "PRESDEM2028"),
    ],
)
def test_kalshi_url_shapes(url: str, ticker: str):
    assert KalshiSource.parse_url(url) == ticker


@pytest.mark.parametrize(
    "url",
    [
        "https://manifold.markets/foo",
        "https://example.com/some/path",
        "not-a-url",
        "ftp://polymarket.com/market/x",
    ],
)
def test_detect_exchange_rejects_unknown(url: str):
    if url.startswith(("http://", "https://", "ftp://")):
        with pytest.raises(UnsupportedURLError):
            detect_exchange(url)
    else:
        # Bare strings without scheme just don't match anything
        with pytest.raises(UnsupportedURLError):
            detect_exchange(url)


def test_detect_exchange_polymarket():
    assert detect_exchange("https://polymarket.com/market/x") == "polymarket"
    assert detect_exchange("https://www.polymarket.com/market/x") == "polymarket"


def test_detect_exchange_kalshi():
    assert detect_exchange("https://kalshi.com/markets/X") == "kalshi"


def test_polymarket_rejects_kalshi_url():
    with pytest.raises(UnsupportedURLError):
        PolymarketSource.parse_url("https://kalshi.com/markets/X")


def test_kalshi_rejects_polymarket_url():
    with pytest.raises(UnsupportedURLError):
        KalshiSource.parse_url("https://polymarket.com/market/x")
