"""SimilarityRetriever agent: lexical search across cross-exchange titles via pg_trgm."""

from __future__ import annotations

import logging

from sqlalchemy import desc, func, select

from app.agents.state import CompareState
from app.config import get_settings
from app.db import models as m
from app.db.base import get_session_ctx
from app.db.models import Exchange
from app.schemas.market import Candidate, NormalizedMarket

logger = logging.getLogger(__name__)


async def similarity_retriever_node(state: CompareState) -> CompareState:
    events = state.get("events", [])
    market = state.get("input_market")
    if market is None:
        events.append({"step": "retriever", "status": "skipped", "reason": "no input market"})
        return {**state, "events": events}

    settings = get_settings()
    events.append({"step": "retriever", "status": "start"})
    try:
        query_text = (market.title or "").strip()
        if not query_text:
            events.append(
                {"step": "retriever", "status": "skipped", "reason": "empty input title"}
            )
            return {**state, "events": events}

        opposite = (
            Exchange.kalshi if market.exchange == "polymarket" else Exchange.polymarket
        )

        candidates: list[Candidate] = []
        nearest_below: tuple[float, str] | None = None
        with get_session_ctx() as session:
            opposite_count = (
                session.scalar(
                    select(func.count())
                    .select_from(m.Market)
                    .where(m.Market.exchange == opposite)
                )
                or 0
            )

            sim_expr = func.similarity(m.Market.title, query_text).label("similarity")
            stmt = (
                select(m.Market, sim_expr)
                .where(m.Market.exchange == opposite)
                .order_by(desc(sim_expr))
                .limit(settings.similarity_top_k * 2)
            )
            rows = session.execute(stmt).all()

            for db_market, similarity in rows:
                score = float(similarity or 0.0)
                if score < settings.similarity_min_score:
                    if nearest_below is None:
                        nearest_below = (score, db_market.title or "")
                    continue
                normalized = NormalizedMarket(
                    exchange=db_market.exchange.value,
                    external_id=db_market.external_id,
                    slug_or_ticker=db_market.slug_or_ticker,
                    title=db_market.title,
                    description_raw=db_market.description_raw or "",
                    rules_raw=db_market.rules_raw or {},
                    resolution_source=db_market.resolution_source,
                    expiration_ts=db_market.expiration_ts,
                    status=db_market.status.value if db_market.status else "unknown",
                    url=db_market.url,
                )
                candidates.append(
                    Candidate(
                        market_id=str(db_market.id),
                        exchange=db_market.exchange.value,
                        external_id=db_market.external_id,
                        title=db_market.title,
                        url=db_market.url,
                        similarity=round(score, 4),
                        market=normalized,
                    )
                )
                if len(candidates) >= settings.similarity_top_k:
                    break

        retriever_event: dict = {
            "step": "retriever",
            "status": "ok",
            "candidates": len(candidates),
        }
        if not candidates:
            diag: dict = {
                "opposite_exchange_market_count": opposite_count,
                "similarity_floor": settings.similarity_min_score,
                "search_kind": "pg_trgm",
            }
            if opposite_count == 0:
                diag["hint"] = (
                    "No markets ingested yet for the other exchange. Run "
                    "POST /admin/ingest (with x-admin-token) to populate the catalog."
                )
            elif nearest_below is not None:
                best_score, best_title = nearest_below
                diag["nearest_similarity_below_floor"] = round(best_score, 4)
                diag["nearest_title"] = best_title[:120]
                diag["hint"] = (
                    f"Nearest neighbor similarity is {round(best_score, 4)}, below "
                    f"SIMILARITY_MIN_SCORE={settings.similarity_min_score}; lower the "
                    "floor in .env or wait for fuller catalog ingest."
                )
            else:
                diag["hint"] = (
                    "Lexical search returned no rows; the opposite exchange catalog "
                    "may still be ingesting."
                )
            retriever_event["diagnostics"] = diag

        events.append(retriever_event)
        return {**state, "candidates": candidates, "events": events}
    except Exception as e:
        logger.exception("SimilarityRetriever failed")
        errors = state.get("errors", [])
        errors.append(f"retriever: {e}")
        events.append({"step": "retriever", "status": "error", "message": str(e)})
        return {**state, "errors": errors, "events": events}
