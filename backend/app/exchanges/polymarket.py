"""Polymarket Gamma API adapter."""

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
    v = value.strip().rstrip("Z")
    try:
        return datetime.fromisoformat(v + ("+00:00" if "+" not in v and "-" not in v[10:] else ""))
    except ValueError:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


def _is_gamma_market_id(identifier: str) -> bool:
    """True if `identifier` looks like a Gamma /markets/{id} key (not a slug string)."""
    s = identifier.strip()
    if not s:
        return False
    if s.startswith("0x") and len(s) >= 12:
        return all(c in "0123456789abcdefABCDEF" for c in s[2:])
    return s.isdigit()


def _first_market_dict(data: Any) -> dict[str, Any] | None:
    if isinstance(data, list):
        if not data:
            return None
        first = data[0]
        return first if isinstance(first, dict) else None
    if isinstance(data, dict):
        return data
    return None


def _pick_market_from_list(items: list[Any], slug: str) -> dict[str, Any] | None:
    for m in items:
        if isinstance(m, dict) and m.get("slug") == slug:
            return m
    for m in items:
        if isinstance(m, dict):
            return m
    return None


def _normalize(raw: dict[str, Any]) -> NormalizedMarket:
    slug = raw.get("slug") or ""
    return NormalizedMarket(
        exchange="polymarket",
        external_id=str(raw.get("conditionId") or raw.get("id") or slug),
        slug_or_ticker=slug,
        title=str(raw.get("question") or raw.get("title") or slug),
        description_raw=str(raw.get("description") or ""),
        rules_raw={
            "resolution_source": raw.get("resolutionSource") or "",
            "category": raw.get("category") or "",
            "groupItemTitle": raw.get("groupItemTitle") or "",
            "outcomes": raw.get("outcomes") or "",
        },
        resolution_source=raw.get("resolutionSource") or None,
        expiration_ts=_parse_iso(raw.get("endDate")),
        status=("closed" if raw.get("closed") else ("open" if raw.get("active") else "unknown")),
        url=f"https://polymarket.com/market/{slug}" if slug else None,
    )


class PolymarketSource(MarketSource):
    name = "polymarket"

    @classmethod
    def parse_url(cls, url: str) -> str:
        u = urlparse(url)
        if u.scheme not in {"http", "https"}:
            raise UnsupportedURLError(f"URL must be http(s): {url}")
        if "polymarket.com" not in (u.hostname or ""):
            raise UnsupportedURLError(f"Not a Polymarket URL: {url}")
        parts = [p for p in (u.path or "").split("/") if p]
        if not parts:
            raise UnsupportedURLError(f"Polymarket URL has no path: {url}")
        # Common shapes:
        #   /market/{slug}
        #   /markets/{slug}               (some frontend URLs use plural)
        #   /event/{event-slug}/{market-slug}
        #   /event/{event-slug}            (event-only; we use the event slug as best-effort)
        if parts[0] == "market" and len(parts) >= 2:
            return parts[1]
        if parts[0] == "markets" and len(parts) >= 2:
            return parts[1]
        if parts[0] == "event":
            return parts[2] if len(parts) >= 3 else parts[1]
        return parts[-1]

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._settings = get_settings()
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=str(self._settings.polymarket_base),
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
        ident = identifier.strip()

        async def market_from_response(resp: httpx.Response) -> NormalizedMarket | None:
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            raw = _first_market_dict(resp.json())
            return _normalize(raw) if raw else None

        # 1) Canonical slug path (Gamma docs: GET /markets/slug/{slug})
        resp = await client.get(f"/markets/slug/{ident}")
        if resp.status_code != 404:
            m = await market_from_response(resp)
            if m is not None:
                return m

        # 2) Query form (same docs: GET /markets?slug=...)
        resp = await client.get("/markets", params={"slug": ident, "limit": 10})
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, list):
                picked = _pick_market_from_list(body, ident)
                if picked:
                    return _normalize(picked)

        # 3) Event slug — multi-outcome pages; market slug endpoint may 404
        resp = await client.get(f"/events/slug/{ident}")
        if resp.status_code == 200:
            ev = resp.json()
            if isinstance(ev, dict):
                mkts = ev.get("markets")
                if isinstance(mkts, list) and mkts:
                    picked = _pick_market_from_list(mkts, ident)
                    raw = picked or (mkts[0] if isinstance(mkts[0], dict) else None)
                    if raw:
                        return _normalize(raw)
        elif resp.status_code not in (404,):
            resp.raise_for_status()

        resp = await client.get("/events", params={"slug": ident, "limit": 5})
        if resp.status_code == 200:
            evs = resp.json()
            if isinstance(evs, list) and evs and isinstance(evs[0], dict):
                mkts = evs[0].get("markets")
                if isinstance(mkts, list) and mkts:
                    picked = _pick_market_from_list(mkts, ident)
                    raw = picked or (mkts[0] if isinstance(mkts[0], dict) else None)
                    if raw:
                        return _normalize(raw)

        # 4) Only /markets/{id} for real Gamma ids — slugs yield 422 Unprocessable Entity
        if _is_gamma_market_id(ident):
            resp = await client.get(f"/markets/{ident}")
            m = await market_from_response(resp)
            if m is not None:
                return m

        raise MarketNotFoundError(f"Polymarket market not found: {ident}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=4),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    async def list_open(self, cursor: str | None = None, limit: int = 500) -> Page[NormalizedMarket]:
        client = await self._get_client()
        offset = int(cursor) if cursor else 0
        resp = await client.get(
            "/markets",
            params={
                "active": "true",
                "closed": "false",
                "limit": str(limit),
                "offset": str(offset),
            },
        )
        resp.raise_for_status()
        data = resp.json()
        items = [_normalize(m) for m in (data or []) if isinstance(m, dict)]
        next_cursor = str(offset + limit) if len(items) >= limit else None
        return Page(items=items, next_cursor=next_cursor)
