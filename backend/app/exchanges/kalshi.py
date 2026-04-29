"""Kalshi v2 public API adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config import get_settings
from app.exchanges.base import (
    MarketNotFoundError,
    MarketSource,
    Page,
    UnsupportedURLError,
)
from app.schemas.market import NormalizedMarket


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _kalshi_status_to_market_status(status: str | None) -> str:
    s = (status or "").lower()
    if s in {"open", "active", "initialized"}:
        return "open"
    if s in {"closed", "settling"}:
        return "closed"
    if s in {"finalized", "settled", "resolved"}:
        return "resolved"
    return "unknown"


def _normalize(raw: dict[str, Any]) -> NormalizedMarket:
    ticker = str(raw.get("ticker") or "")
    title = str(raw.get("title") or raw.get("yes_sub_title") or ticker)
    rules_primary = str(raw.get("rules_primary") or "")
    rules_secondary = str(raw.get("rules_secondary") or "")
    description = "\n\n".join(p for p in (rules_primary, rules_secondary) if p) or title
    return NormalizedMarket(
        exchange="kalshi",
        external_id=ticker,
        slug_or_ticker=ticker,
        title=title,
        description_raw=description,
        rules_raw={
            "rules_primary": rules_primary,
            "rules_secondary": rules_secondary,
            "category": raw.get("category") or "",
            "subtitle": raw.get("subtitle") or "",
            "yes_sub_title": raw.get("yes_sub_title") or "",
            "no_sub_title": raw.get("no_sub_title") or "",
            "settlement_timer_seconds": raw.get("settlement_timer_seconds"),
        },
        resolution_source=None,
        expiration_ts=_parse_iso(raw.get("expiration_time") or raw.get("close_time")),
        status=_kalshi_status_to_market_status(raw.get("status")),
        url=f"https://kalshi.com/markets/{ticker.lower()}" if ticker else None,
    )


class KalshiSource(MarketSource):
    name = "kalshi"

    @classmethod
    def parse_url(cls, url: str) -> str:
        u = urlparse(url)
        if u.scheme not in {"http", "https"}:
            raise UnsupportedURLError(f"URL must be http(s): {url}")
        if "kalshi.com" not in (u.hostname or ""):
            raise UnsupportedURLError(f"Not a Kalshi URL: {url}")
        parts = [p for p in (u.path or "").split("/") if p]
        if not parts:
            raise UnsupportedURLError(f"Kalshi URL has no path: {url}")
        # URL shapes seen in the wild:
        #   /markets/{ticker}
        #   /markets/{series}/{event-or-ticker}
        #   /events/{event-ticker}/{market-ticker}
        if parts[0] in {"markets", "events"}:
            tail = parts[-1]
            return tail.upper()
        return parts[-1].upper()

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._settings = get_settings()
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=str(self._settings.kalshi_base),
                timeout=20.0,
                headers={"accept": "application/json"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=4),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def fetch(self, identifier: str) -> NormalizedMarket:
        client = await self._get_client()
        ticker = identifier.upper()
        resp = await client.get(f"/markets/{ticker}")
        if resp.status_code == 404:
            raise MarketNotFoundError(f"Kalshi market not found: {ticker}")
        resp.raise_for_status()
        data = resp.json()
        market = data.get("market") if isinstance(data, dict) else None
        if not market:
            raise MarketNotFoundError(f"Kalshi response missing 'market' key for {ticker}")
        return _normalize(market)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=4),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def list_open(self, cursor: str | None = None, limit: int = 200) -> Page[NormalizedMarket]:
        client = await self._get_client()
        params: dict[str, str] = {"status": "open", "limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get("/markets", params=params)
        resp.raise_for_status()
        data = resp.json()
        items = [_normalize(m) for m in (data.get("markets") or []) if isinstance(m, dict)]
        next_cursor = data.get("cursor") or None
        # Kalshi returns the same cursor at end-of-pagination; treat empty-page as terminal.
        if not items:
            next_cursor = None
        return Page(items=items, next_cursor=next_cursor)
