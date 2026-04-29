"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.v1 import admin, compare, health, markets
from app.config import get_settings
from app.db.base import init_engine
from app.services.catalog_ingester import CatalogIngester

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    init_engine()

    ingester = CatalogIngester()
    app.state.ingester = ingester
    if settings.ingest_on_startup:
        await ingester.start()
    yield
    await ingester.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="RuleC: Cross-Platform Prediction Market Rules Comparer",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/healthz", tags=["health"])
    app.include_router(compare.router, prefix="/api/v1/compare", tags=["compare"])
    app.include_router(markets.router, prefix="/api/v1/markets", tags=["markets"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    return app


def _rate_limit_handler(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})


app = create_app()
