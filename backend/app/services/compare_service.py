"""High-level orchestration for a compare run, persisting state to the comparisons table."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from app.agents.state import new_state
from app.agents.supervisor import _get_compiled  # type: ignore
from app.agents.risk_synthesizer import build_risk_matrix_payload
from app.db import models as m
from app.db.base import get_session_ctx

logger = logging.getLogger(__name__)


def create_comparison(url: str) -> str:
    with get_session_ctx() as session:
        row = m.Comparison(input_url=url, status=m.ComparisonStatus.pending)
        session.add(row)
        session.flush()
        cid = str(row.id)
        session.commit()
        return cid


def _set_status(comparison_id: str, **fields) -> None:
    with get_session_ctx() as session:
        row = session.get(m.Comparison, uuid.UUID(comparison_id))
        if row is None:
            return
        for k, v in fields.items():
            setattr(row, k, v)
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()


def _persist_candidates(comparison_id: str, payload: dict) -> None:
    rows = payload.get("rows", [])
    if not rows:
        return
    with get_session_ctx() as session:
        cmp_uuid = uuid.UUID(comparison_id)
        for row in rows:
            cand = row.get("candidate") or {}
            mid = cand.get("market_id")
            if not mid:
                continue
            try:
                cand_uuid = uuid.UUID(mid)
            except (TypeError, ValueError):
                continue
            session.add(
                m.ComparisonCandidate(
                    comparison_id=cmp_uuid,
                    candidate_market_id=cand_uuid,
                    similarity=float(cand.get("similarity") or 0.0),
                    divergences=row,
                )
            )
        session.commit()


async def run_comparison(comparison_id: str, url: str) -> dict:
    _set_status(comparison_id, status=m.ComparisonStatus.running)
    try:
        compiled = _get_compiled()
        final_state = await compiled.ainvoke(new_state(url))
        payload = build_risk_matrix_payload(final_state)
        payload["errors"] = final_state.get("errors", [])
        payload["events"] = final_state.get("events", [])

        input_market_id = final_state.get("input_market_id")
        input_uuid = uuid.UUID(input_market_id) if input_market_id else None

        if final_state.get("errors") and not final_state.get("input_market"):
            _set_status(
                comparison_id,
                status=m.ComparisonStatus.error,
                error="; ".join(final_state["errors"]),
                risk_matrix=payload,
                input_market_id=input_uuid,
            )
        else:
            _set_status(
                comparison_id,
                status=m.ComparisonStatus.done,
                risk_matrix=payload,
                input_market_id=input_uuid,
            )
            _persist_candidates(comparison_id, payload)
        return payload
    except Exception as e:
        logger.exception("Comparison run failed")
        _set_status(comparison_id, status=m.ComparisonStatus.error, error=str(e))
        raise


async def stream_comparison(comparison_id: str, url: str) -> AsyncIterator[dict]:
    """Yield per-step events while running. Persists final result at the end."""
    _set_status(comparison_id, status=m.ComparisonStatus.running)
    yield {"type": "started", "data": {"comparison_id": comparison_id, "url": url}}

    try:
        compiled = _get_compiled()
        last_seen = 0
        last_chunk: dict = {}
        async for chunk in compiled.astream(new_state(url), stream_mode="values"):
            last_chunk = chunk
            events = chunk.get("events", [])
            for event in events[last_seen:]:
                yield {"type": "step", "data": event}
            last_seen = len(events)

        payload = build_risk_matrix_payload(last_chunk)
        payload["errors"] = last_chunk.get("errors", [])
        payload["events"] = last_chunk.get("events", [])
        input_market_id = last_chunk.get("input_market_id")
        input_uuid = uuid.UUID(input_market_id) if input_market_id else None

        if last_chunk.get("errors") and not last_chunk.get("input_market"):
            _set_status(
                comparison_id,
                status=m.ComparisonStatus.error,
                error="; ".join(last_chunk["errors"]),
                risk_matrix=payload,
                input_market_id=input_uuid,
            )
            yield {"type": "error", "data": last_chunk["errors"][-1]}
        else:
            _set_status(
                comparison_id,
                status=m.ComparisonStatus.done,
                risk_matrix=payload,
                input_market_id=input_uuid,
            )
            _persist_candidates(comparison_id, payload)
            yield {"type": "result", "data": payload}
    except Exception as e:
        logger.exception("Comparison stream failed")
        _set_status(comparison_id, status=m.ComparisonStatus.error, error=str(e))
        yield {"type": "error", "data": str(e)}
