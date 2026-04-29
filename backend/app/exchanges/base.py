"""Common abstractions for exchange adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, Iterable, TypeVar
from urllib.parse import urlparse

from app.schemas.market import ExchangeName, NormalizedMarket

T = TypeVar("T")


class UnsupportedURLError(ValueError):
    """Raised when a URL cannot be mapped to any known exchange."""


class MarketNotFoundError(LookupError):
    """Raised when an exchange API returns no market for the given identifier."""


@dataclass
class Page(Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class MarketSource(ABC):
    """Abstract base for an exchange adapter."""

    name: ExchangeName

    @classmethod
    @abstractmethod
    def parse_url(cls, url: str) -> str:
        """Return the slug or ticker identifying the market in the URL."""

    @abstractmethod
    async def fetch(self, identifier: str) -> NormalizedMarket:
        """Fetch a single market and normalize it."""

    @abstractmethod
    async def list_open(self, cursor: str | None = None, limit: int = 100) -> Page[NormalizedMarket]:
        """Page through currently-open markets."""


def detect_exchange(url: str) -> ExchangeName:
    """Infer which exchange a market URL points at."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsupportedURLError(f"URL must be http(s): {url}")
    host = (parsed.hostname or "").lower()
    if "polymarket.com" in host:
        return "polymarket"
    if "kalshi.com" in host:
        return "kalshi"
    raise UnsupportedURLError(f"URL does not match a supported exchange: {url}")


def get_source(exchange: ExchangeName) -> MarketSource:
    """Factory that returns a fresh adapter instance."""
    from app.exchanges.kalshi import KalshiSource
    from app.exchanges.polymarket import PolymarketSource

    if exchange == "polymarket":
        return PolymarketSource()
    if exchange == "kalshi":
        return KalshiSource()
    raise UnsupportedURLError(f"Unknown exchange: {exchange}")


def all_sources() -> Iterable[MarketSource]:
    return [get_source("polymarket"), get_source("kalshi")]
