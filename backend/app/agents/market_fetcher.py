"""MarketFetcher agent: parse URL, fetch the input market, normalize it."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.agents.state import CompareState
from app.db import models as m
from app.db.base import get_session_ctx
from app.exchanges import detect_exchange, get_source

logger = logging.getLogger(__name__)


async def market_fetcher_node(state: CompareState) -> CompareState:
    url = state["input_url"]
    events = state.get("events", [])
    events.append({"step": "fetcher", "status": "start", "url": url})
    try:
        exchange = detect_exchange(url)
        source = get_source(exchange)
        try:
            identifier = source.parse_url(url)
            market = await source.fetch(identifier)
        finally:
            if hasattr(source, "aclose"):
                await source.aclose()  # type: ignore[func-returns-value]

        market_id = _upsert_input_market(market)
        events.append(
            {
                "step": "fetcher",
                "status": "ok",
                "exchange": exchange,
                "title": market.title,
                "market_id": market_id,
            }
        )
        return {
            **state,
            "input_market": market,
            "input_market_id": market_id,
            "events": events,
        }
    except Exception as e:
        logger.exception("MarketFetcher failed")
        errors = state.get("errors", [])
        errors.append(f"fetcher: {e}")
        events.append({"step": "fetcher", "status": "error", "message": str(e)})
        return {**state, "errors": errors, "events": events}


def _upsert_input_market(market) -> str:
    """Persist (or refresh) the input market and return its DB UUID as a string."""
    with get_session_ctx() as session:
        now = datetime.now(timezone.utc)
        stmt = pg_insert(m.Market).values(
            exchange=market.exchange,
            external_id=market.external_id,
            slug_or_ticker=market.slug_or_ticker,
            url=market.url,
            title=market.title,
            description_raw=market.description_raw,
            rules_raw=market.rules_raw,
            resolution_source=market.resolution_source,
            expiration_ts=market.expiration_ts,
            status=market.status if market.status in {"open", "closed", "resolved", "unknown"} else "unknown",
            last_synced_at=now,
        )
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
        ).returning(m.Market.id)
        row = session.execute(stmt).first()
        if row is None:
            row = session.execute(
                select(m.Market.id).where(
                    m.Market.exchange == market.exchange,
                    m.Market.external_id == market.external_id,
                )
            ).first()
        session.commit()
        return str(row.id)
