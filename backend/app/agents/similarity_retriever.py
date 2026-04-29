"""SimilarityRetriever agent: embed input market, fetch cross-exchange neighbors."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.agents.state import CompareState
from app.config import get_settings
from app.db import models as m
from app.db.base import get_session_ctx
from app.embeddings import get_embedder
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
        embedder = get_embedder()
        query_vec = await embedder.embed_query(market.embedding_text())

        with get_session_ctx() as session:
            distance = m.MarketEmbedding.embedding.cosine_distance(query_vec)
            stmt = (
                select(m.Market, distance.label("distance"))
                .join(m.MarketEmbedding, m.MarketEmbedding.market_id == m.Market.id)
                .where(m.Market.exchange != market.exchange)
                .order_by(distance)
                .limit(settings.similarity_top_k * 2)
            )
            rows = session.execute(stmt).all()

        candidates: list[Candidate] = []
        for db_market, distance in rows:
            similarity = 1.0 - float(distance)
            if similarity < settings.similarity_min_score:
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
                    similarity=round(similarity, 4),
                    market=normalized,
                )
            )
            if len(candidates) >= settings.similarity_top_k:
                break

        events.append(
            {"step": "retriever", "status": "ok", "candidates": len(candidates)}
        )
        return {**state, "candidates": candidates, "events": events}
    except Exception as e:
        logger.exception("SimilarityRetriever failed")
        errors = state.get("errors", [])
        errors.append(f"retriever: {e}")
        events.append({"step": "retriever", "status": "error", "message": str(e)})
        return {**state, "errors": errors, "events": events}
