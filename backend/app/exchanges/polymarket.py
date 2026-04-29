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
        #   /event/{event-slug}/{market-slug}
        #   /event/{event-slug}            (event-only; we use the event slug as best-effort)
        if parts[0] == "market" and len(parts) >= 2:
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
        # Try slug first, then fall back to id.
        for path in (f"/markets/slug/{identifier}", f"/markets/{identifier}"):
            resp = await client.get(path)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                if not data:
                    continue
                data = data[0]
            return _normalize(data)
        raise MarketNotFoundError(f"Polymarket market not found: {identifier}")

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
