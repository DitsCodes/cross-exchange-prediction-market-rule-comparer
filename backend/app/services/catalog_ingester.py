"""Background job that keeps Postgres+pgvector fresh with open markets from both exchanges."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db import models as m
from app.db.base import get_session_ctx
from app.embeddings import get_embedder
from app.exchanges import all_sources
from app.exchanges.base import MarketSource
from app.schemas.market import NormalizedMarket

logger = logging.getLogger(__name__)


@dataclass
class IngestStats:
    polymarket: int = 0
    kalshi: int = 0
    embedded: int = 0
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
                    "Ingest complete: polymarket=%d kalshi=%d embedded=%d errors=%d",
                    stats.polymarket,
                    stats.kalshi,
                    stats.embedded,
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
            if not page.items:
                break
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
            existing_ids: dict[tuple[str, str], tuple[str, str]] = {}
            keys = [(it.exchange, it.external_id) for it in items]
            rows = session.execute(
                select(m.Market.id, m.Market.exchange, m.Market.external_id, m.Market.title).where(
                    m.Market.exchange.in_({k[0] for k in keys})
                )
            ).all()
            for row in rows:
                existing_ids[(row.exchange.value, row.external_id)] = (str(row.id), row.title)

            insert_payload = []
            for it in items:
                insert_payload.append(
                    {
                        "exchange": it.exchange,
                        "external_id": it.external_id,
                        "slug_or_ticker": it.slug_or_ticker,
                        "url": it.url,
                        "title": it.title,
                        "description_raw": it.description_raw,
                        "rules_raw": it.rules_raw,
                        "resolution_source": it.resolution_source,
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
            ).returning(m.Market.id, m.Market.exchange, m.Market.external_id, m.Market.title)

            inserted = session.execute(stmt).all()
            session.commit()

            id_by_key = {(row.exchange.value, row.external_id): str(row.id) for row in inserted}

            to_embed: list[NormalizedMarket] = []
            ids: list[str] = []
            for it in items:
                key = (it.exchange, it.external_id)
                mid = id_by_key.get(key)
                if not mid:
                    continue
                prev_title = existing_ids.get(key, (None, None))[1]
                if prev_title is None or prev_title != it.title:
                    to_embed.append(it)
                    ids.append(mid)

            await self._embed_and_store(session, ids, to_embed, stats)

    async def _embed_and_store(
        self,
        session,
        market_ids: list[str],
        markets: list[NormalizedMarket],
        stats: IngestStats,
    ) -> None:
        if not markets or not self._settings.voyage_api_key:
            return
        embedder = get_embedder()
        texts = [mkt.embedding_text() for mkt in markets]
        try:
            vectors = await embedder.embed_documents(texts)
        except Exception as e:
            logger.warning("Embedding batch failed: %s", e)
            stats.errors.append(f"embed: {e!r}")
            return

        rows = [
            {
                "market_id": mid,
                "embedding": vec,
                "model": self._settings.voyage_model,
            }
            for mid, vec in zip(market_ids, vectors)
        ]
        stmt = pg_insert(m.MarketEmbedding).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["market_id"],
            set_={
                "embedding": stmt.excluded.embedding,
                "model": stmt.excluded.model,
            },
        )
        session.execute(stmt)
        session.commit()
        stats.embedded += len(rows)
