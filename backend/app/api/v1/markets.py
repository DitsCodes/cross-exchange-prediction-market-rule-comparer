"""Markets endpoints (debug / inspection)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.exchanges import get_source
from app.exchanges.base import MarketNotFoundError, UnsupportedURLError
from app.schemas.market import ExchangeName, NormalizedMarket

router = APIRouter()


@router.get("/{exchange}/{identifier}", response_model=NormalizedMarket)
async def fetch_market(exchange: ExchangeName, identifier: str) -> NormalizedMarket:
    try:
        source = get_source(exchange)
    except UnsupportedURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        try:
            return await source.fetch(identifier)
        except MarketNotFoundError:
            raise HTTPException(status_code=404, detail="market not found")
    finally:
        if hasattr(source, "aclose"):
            await source.aclose()  # type: ignore[func-returns-value]
