"""Lexical (pg_trgm) similarity retriever tests."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.agents import similarity_retriever as retriever
from app.db.models import Exchange, MarketStatus
from app.schemas.market import NormalizedMarket


@dataclass
class FakeMarket:
    title: str
    description_raw: str = ""
    rules_raw: dict | None = None
    resolution_source: str | None = None
    expiration_ts = None
    status: MarketStatus = MarketStatus.open
    url: str | None = None
    external_id: str = "ext-1"
    slug_or_ticker: str = "slug-1"
    exchange: Exchange = Exchange.kalshi
    id = uuid4()


class FakeRows:
    def __init__(self, rows: list[tuple[FakeMarket, float]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[FakeMarket, float]]:
        return list(self._rows)


class FakeSession:
    def __init__(self, opposite_count: int, rows: list[tuple[FakeMarket, float]]) -> None:
        self.opposite_count = opposite_count
        self.rows = rows
        self.last_sql = ""

    def scalar(self, stmt):
        return self.opposite_count

    def execute(self, stmt):
        self.last_sql = str(stmt)
        return FakeRows(self.rows)


class FakeSessionCtx:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __enter__(self) -> FakeSession:
        return self.session

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _input_market() -> NormalizedMarket:
    return NormalizedMarket(
        exchange="polymarket",
        external_id="pm-1",
        slug_or_ticker="pm-1",
        title="Will candidate win the election?",
    )


async def test_retriever_returns_candidates_above_floor(monkeypatch) -> None:
    rows = [
        (FakeMarket(title="Will candidate win election?"), 0.55),
        (FakeMarket(title="Tangentially related market", external_id="ext-2"), 0.10),
    ]
    fake_session = FakeSession(opposite_count=2, rows=rows)
    monkeypatch.setattr(retriever, "get_session_ctx", lambda: FakeSessionCtx(fake_session))

    state = {"events": [], "input_market": _input_market()}
    result = await retriever.similarity_retriever_node(state)

    assert "similarity" in fake_session.last_sql.lower()
    assert len(result["candidates"]) == 1
    cand = result["candidates"][0]
    assert cand.similarity == 0.55
    assert cand.exchange == "kalshi"

    last_event = result["events"][-1]
    assert last_event["status"] == "ok"
    assert last_event["candidates"] == 1


async def test_retriever_emits_diagnostics_when_floor_blocks_everything(monkeypatch) -> None:
    rows = [(FakeMarket(title="Loosely related"), 0.05)]
    fake_session = FakeSession(opposite_count=12, rows=rows)
    monkeypatch.setattr(retriever, "get_session_ctx", lambda: FakeSessionCtx(fake_session))

    state = {"events": [], "input_market": _input_market()}
    result = await retriever.similarity_retriever_node(state)

    assert result["candidates"] == []
    diag = result["events"][-1]["diagnostics"]
    assert diag["opposite_exchange_market_count"] == 12
    assert diag["search_kind"] == "pg_trgm"
    assert diag["nearest_similarity_below_floor"] == 0.05
    assert "lower the floor" in diag["hint"].lower()


async def test_retriever_diagnoses_empty_opposite_catalog(monkeypatch) -> None:
    fake_session = FakeSession(opposite_count=0, rows=[])
    monkeypatch.setattr(retriever, "get_session_ctx", lambda: FakeSessionCtx(fake_session))

    state = {"events": [], "input_market": _input_market()}
    result = await retriever.similarity_retriever_node(state)

    assert result["candidates"] == []
    diag = result["events"][-1]["diagnostics"]
    assert diag["opposite_exchange_market_count"] == 0
    assert "/admin/ingest" in diag["hint"]
