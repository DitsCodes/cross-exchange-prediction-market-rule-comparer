"""Admin endpoints (manual ingest trigger, etc.)."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import get_settings

router = APIRouter()


@router.post("/ingest")
async def admin_ingest(request: Request, x_admin_token: str = Header(default="")):
    settings = get_settings()
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="invalid admin token")
    ingester = getattr(request.app.state, "ingester", None)
    if ingester is None:
        raise HTTPException(status_code=503, detail="ingester not initialized")
    stats = await ingester.run_once()
    return {
        "polymarket": stats.polymarket,
        "kalshi": stats.kalshi,
        "errors": stats.errors,
    }
