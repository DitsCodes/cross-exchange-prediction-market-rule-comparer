"""Background job that keeps Postgres fresh with open markets from both exchanges."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db import models as m
from app.db.base import get_session_ctx
from app.exchanges import all_sources
from app.exchanges.base import MarketSource
from app.schemas.market import NormalizedMarket

logger = logging.getLogger(__name__)


@dataclass
class IngestStats:
    polymarket: int = 0
    kalshi: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


class CatalogIngester:
    """Drives the periodic catalog refresh."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._scheduler: AsyncIOScheduler | None = None
        self._lock = asyncio.Lock()
        self._last_stats: IngestStats | None = None

    async def start(self) -> None:
        if self._scheduler is not None:
            return
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._scheduler.add_job(
            self.run_once,
            "interval",
            minutes=self._settings.ingest_interval_minutes,
            next_run_time=datetime.now(timezone.utc),
            id="catalog_ingester",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info(
            "Catalog ingester started; refreshing every %s min.",
            self._settings.ingest_interval_minutes,
        )

    async def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    @property
    def last_stats(self) -> IngestStats | None:
        return self._last_stats

    async def run_once(self) -> IngestStats:
        if self._lock.locked():
            logger.info("Ingester already running; skipping overlap.")
            return self._last_stats or IngestStats()

        async with self._lock:
            stats = IngestStats()
            try:
                for source in all_sources():
                    try:
                        count = await self._ingest_source(source, stats)
                        if source.name == "polymarket":
                            stats.polymarket = count
                        elif source.name == "kalshi":
                            stats.kalshi = count
                    except Exception as e:
                        msg = f"{source.name}: {e!r}"
                        logger.exception("Ingest failed for %s", source.name)
                        stats.errors.append(msg)
                    finally:
                        if hasattr(source, "aclose"):
                            await source.aclose()  # type: ignore[func-returns-value]
            finally:
                stats.finished_at = datetime.now(timezone.utc)
                self._last_stats = stats
                logger.info(
                    "Ingest complete: polymarket=%d kalshi=%d errors=%d",
                    stats.polymarket,
                    stats.kalshi,
                    len(stats.errors),
                )
            return stats

    async def _ingest_source(self, source: MarketSource, stats: IngestStats) -> int:
        page_size = (
            self._settings.ingest_polymarket_page_size
            if source.name == "polymarket"
            else self._settings.ingest_kalshi_page_size
        )
        cursor: str | None = None
        total = 0
        for _ in range(self._settings.ingest_max_pages):
            page = await source.list_open(cursor=cursor, limit=page_size)
            if page.items:
                await self._upsert_batch(page.items, stats)
                total += len(page.items)
            if not page.next_cursor:
                break
            cursor = page.next_cursor
        return total

    async def _upsert_batch(self, items: list[NormalizedMarket], stats: IngestStats) -> None:
        if not items:
            return

        with get_session_ctx() as session:
            now = datetime.now(timezone.utc)

            insert_payload = []
            for it in items:
                insert_payload.append(
                    {
                        "exchange": it.exchange,
                        "external_id": _fit_column(it.external_id, 255),
                        "slug_or_ticker": _fit_column(it.slug_or_ticker, 512),
                        "url": _fit_column(it.url, 1024),
                        "title": _fit_column(it.title, 1024),
                        "description_raw": it.description_raw,
                        "rules_raw": it.rules_raw,
                        "resolution_source": _fit_column(it.resolution_source, 512),
                        "expiration_ts": it.expiration_ts,
                        "status": it.status if it.status in {"open", "closed", "resolved", "unknown"} else "unknown",
                        "last_synced_at": now,
                    }
                )

            stmt = pg_insert(m.Market).values(insert_payload)
            stmt = stmt.on_conflict_do_update(
                index_elements=["exchange", "external_id"],
                set_={
                    "slug_or_ticker": stmt.excluded.slug_or_ticker,
                    "url": stmt.excluded.url,
                    "title": stmt.excluded.title,
                    "description_raw": stmt.excluded.description_raw,
                    "rules_raw": stmt.excluded.rules_raw,
                    "resolution_source": stmt.excluded.resolution_source,
                    "expiration_ts": stmt.excluded.expiration_ts,
                    "status": stmt.excluded.status,
                    "last_synced_at": stmt.excluded.last_synced_at,
                },
            )

            try:
                session.execute(stmt)
                session.commit()
            except Exception as e:
                session.rollback()
                stats.errors.append(f"upsert: {e!r}")
                logger.exception("Catalog upsert failed for batch of %d markets", len(items))


def _fit_column(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    return value[:max_length]
