"""Compare endpoints: POST /compare, GET /compare/{id}, GET /compare/{id}/stream."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.db import models as m
from app.db.base import get_session
from app.exchanges.base import UnsupportedURLError, detect_exchange
from app.schemas.market import CompareCreated, CompareRequest, CompareResult
from app.services.compare_service import (
    create_comparison,
    run_comparison,
    stream_comparison,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_url(url: str) -> None:
    try:
        detect_exchange(url)
    except UnsupportedURLError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("", response_model=CompareCreated)
async def create_and_run_compare(
    body: CompareRequest, background: BackgroundTasks
) -> CompareCreated:
    _validate_url(body.url)
    cid = create_comparison(body.url)
    background.add_task(run_comparison, cid, body.url)
    return CompareCreated(comparison_id=cid, status="pending")


@router.get("/{comparison_id}", response_model=CompareResult)
async def get_compare(
    comparison_id: str, session: Session = Depends(get_session)
) -> CompareResult:
    try:
        cid = uuid.UUID(comparison_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid comparison id")
    row = session.get(m.Comparison, cid)
    if row is None:
        raise HTTPException(status_code=404, detail="comparison not found")
    return CompareResult(
        comparison_id=str(row.id),
        status=row.status.value,
        risk_matrix=row.risk_matrix,
        error=row.error,
    )


@router.get("/{comparison_id}/stream")
async def stream_compare_endpoint(comparison_id: str, request: Request, url: str = ""):
    """SSE stream of agent steps. The URL is read from the persisted row if not given."""
    try:
        cid_uuid = uuid.UUID(comparison_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid comparison id")

    target_url = url
    if not target_url:
        from app.db.base import get_session_ctx

        with get_session_ctx() as session:
            row = session.get(m.Comparison, cid_uuid)
            if row is None:
                raise HTTPException(status_code=404, detail="comparison not found")
            target_url = row.input_url

    _validate_url(target_url)

    async def event_gen():
        try:
            async for event in stream_comparison(comparison_id, target_url):
                if await request.is_disconnected():
                    break
                yield {"event": event["type"], "data": json.dumps(event["data"])}
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("SSE stream errored")
            yield {"event": "error", "data": json.dumps(str(e))}

    return EventSourceResponse(event_gen())
