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


def _market_url(ticker: str) -> str | None:
    if not ticker:
        return None
    url = f"https://kalshi.com/markets/{ticker.lower()}"
    # Some list responses can include malformed/compound tickers long enough to exceed
    # the DB URL column. URL is optional; keep ingest moving and preserve the ticker.
    return url if len(url) <= 1024 else None


def _is_mve_parlay(raw: dict[str, Any]) -> bool:
    """Detect Kalshi multivariate-event ("MVE") parlay markets.

    These are auto-generated combination markets whose `title` is just the comma-joined
    leg labels (e.g. "yes Leeds United,yes Delhi Capitals,..."), `rules_primary` is empty,
    and tickers/event_tickers carry the documented `KXMVE` prefix. They flood
    `/markets?status=open` and have no question text worth indexing.
    """
    event_ticker = str(raw.get("event_ticker") or "")
    ticker = str(raw.get("ticker") or "")
    if event_ticker.startswith("KXMVE") or ticker.startswith("KXMVE"):
        return True
    if raw.get("mve_selected_legs"):
        return True
    return False


def _build_title(event_title: str, market_title: str, yes_sub: str, n_options: int) -> str:
    """Pick the most matchable title for a Kalshi market.

    - Single-outcome event (binary YES/NO): use the question as-is.
    - Multi-outcome event (e.g. "Who will the next Pope be?" with N candidates):
      append the option's `yes_sub_title` so trigram search can match Polymarket-style
      "Will <X> be <Y>?" questions against the equivalent Kalshi contract.
    """
    base = event_title or market_title
    if n_options > 1 and yes_sub:
        return f"{base} \u2014 {yes_sub}"
    return base


def _normalize(raw: dict[str, Any]) -> NormalizedMarket:
    """Normalize a single market dict (from `/markets/{ticker}` or a list endpoint).

    Used for direct fetch by URL and as a fallback. For multi-outcome contexts the
    catalog ingester prefers `_normalize_event_market` so titles include the option.
    """
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
        url=_market_url(ticker),
    )


def _normalize_event_market(event: dict[str, Any], market: dict[str, Any]) -> NormalizedMarket:
    """Normalize a market that came nested under an event (the `/events` endpoint).

    Pulls rules from either the market or the parent event so the question text and
    resolution rules survive ingestion intact. Constructs a matchable title via
    `_build_title`.
    """
    ticker = str(market.get("ticker") or "")
    event_title = str(event.get("title") or "").strip()
    market_title = str(market.get("title") or "").strip()
    yes_sub = str(market.get("yes_sub_title") or "").strip()
    n_options = len(event.get("markets") or [])

    title = _build_title(event_title, market_title, yes_sub, n_options)
    rules_primary = str(market.get("rules_primary") or event.get("rules_primary") or "")
    rules_secondary = str(market.get("rules_secondary") or event.get("rules_secondary") or "")
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
            "category": event.get("category") or market.get("category") or "",
            "subtitle": event.get("sub_title") or market.get("subtitle") or "",
            "yes_sub_title": yes_sub,
            "no_sub_title": market.get("no_sub_title") or "",
            "event_ticker": event.get("event_ticker") or "",
            "event_title": event_title,
            "series_ticker": event.get("series_ticker") or "",
            "settlement_timer_seconds": market.get("settlement_timer_seconds"),
        },
        resolution_source=None,
        expiration_ts=_parse_iso(market.get("expiration_time") or market.get("close_time")),
        status=_kalshi_status_to_market_status(market.get("status")),
        url=_market_url(ticker),
    )


def _is_mve_event(event: dict[str, Any]) -> bool:
    """Detect Kalshi multivariate-event groupings (auto-generated parlay events).

    These propagate up to /events too; matching their `series_ticker`/`event_ticker`
    by the documented `KXMVE` prefix is the cleanest filter.
    """
    series = str(event.get("series_ticker") or "")
    event_ticker = str(event.get("event_ticker") or "")
    return series.startswith("KXMVE") or event_ticker.startswith("KXMVE")


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
        """Walk Kalshi's `/events` endpoint and yield one NormalizedMarket per nested
        contract. We use `/events` rather than `/markets` because the latter is dominated
        by auto-generated multivariate parlay markets (`KXMVE*`) whose `title` is just
        comma-joined leg labels — they have no question text to search against and
        crowd out real markets across thousands of pages.
        """
        client = await self._get_client()
        params: dict[str, str] = {
            "status": "open",
            "limit": str(limit),
            "with_nested_markets": "true",
        }
        if cursor:
            params["cursor"] = cursor
        resp = await client.get("/events", params=params)
        resp.raise_for_status()
        data = resp.json()
        events = [e for e in (data.get("events") or []) if isinstance(e, dict)]

        items: list[NormalizedMarket] = []
        for event in events:
            if _is_mve_event(event):
                continue
            for market in event.get("markets") or []:
                if not isinstance(market, dict):
                    continue
                if _is_mve_parlay(market):
                    continue
                items.append(_normalize_event_market(event, market))

        next_cursor = data.get("cursor") or None
        # Kalshi returns the same cursor at end-of-pagination; gate on the raw event list
        # so an MVE-saturated page doesn't terminate pagination before real events arrive.
        if not events:
            next_cursor = None
        return Page(items=items, next_cursor=next_cursor)
