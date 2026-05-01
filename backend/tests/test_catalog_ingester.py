"""Catalog ingester safety-rail tests."""

from __future__ import annotations

import pytest

from app.exchanges.base import Page
from app.schemas.market import NormalizedMarket
from app.services.catalog_ingester import CatalogIngester, IngestStats, _fit_column


def test_fit_column_truncates_overlong_values() -> None:
    assert _fit_column("abc", 2) == "ab"


def test_fit_column_passes_short_values_through() -> None:
    assert _fit_column("hello", 32) == "hello"


def test_fit_column_handles_none() -> None:
    assert _fit_column(None, 32) is None


class _FakeSource:
    """Minimal MarketSource stub that emits a scripted sequence of pages."""

    name = "kalshi"

    def __init__(self, pages: list[Page[NormalizedMarket]]) -> None:
        self._pages = pages
        self.calls: list[str | None] = []

    async def list_open(
        self, cursor: str | None = None, limit: int = 200
    ) -> Page[NormalizedMarket]:
        self.calls.append(cursor)
        return self._pages.pop(0)


@pytest.mark.asyncio
async def test_ingest_source_walks_past_empty_filtered_pages(monkeypatch) -> None:
    """An empty `items` list with a live `next_cursor` must NOT terminate pagination
    (regression: prior code broke the loop on `if not page.items`, so a 100% MVE-parlay
    page killed ingest before reaching real markets)."""
    sample = NormalizedMarket(
        exchange="kalshi",
        external_id="REAL-1",
        slug_or_ticker="REAL-1",
        title="Will a Democrat win the 2028 presidential election?",
        description_raw="rules",
        rules_raw={"rules_primary": "rules"},
        resolution_source=None,
        expiration_ts=None,
        status="open",
        url=None,
    )
    pages = [
        Page(items=[], next_cursor="page-2"),
        Page(items=[sample], next_cursor=None),
    ]
    source = _FakeSource(pages)

    ingester = CatalogIngester()
    upserts: list[list[NormalizedMarket]] = []

    async def _capture(items, stats):
        upserts.append(list(items))

    monkeypatch.setattr(ingester, "_upsert_batch", _capture)

    total = await ingester._ingest_source(source, IngestStats())

    assert source.calls == [None, "page-2"]
    assert total == 1
    assert upserts == [[sample]]
