"""SQLAlchemy ORM models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Exchange(str, enum.Enum):
    polymarket = "polymarket"
    kalshi = "kalshi"


class MarketStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    resolved = "resolved"
    unknown = "unknown"


class ComparisonStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Market(Base):
    __tablename__ = "markets"
    __table_args__ = (
        UniqueConstraint("exchange", "external_id", name="uq_markets_exchange_external_id"),
        Index("ix_markets_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exchange: Mapped[Exchange] = mapped_column(
        Enum(Exchange, name="exchange_enum"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    slug_or_ticker: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024))
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description_raw: Mapped[str | None] = mapped_column(Text)
    rules_raw: Mapped[dict | None] = mapped_column(JSON)
    resolution_source: Mapped[str | None] = mapped_column(String(512))
    expiration_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[MarketStatus] = mapped_column(
        Enum(MarketStatus, name="market_status_enum"), default=MarketStatus.unknown, nullable=False
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Comparison(Base):
    __tablename__ = "comparisons"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    input_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    input_market_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("markets.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ComparisonStatus] = mapped_column(
        Enum(ComparisonStatus, name="comparison_status_enum"),
        default=ComparisonStatus.pending,
        nullable=False,
    )
    risk_matrix: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    candidates: Mapped[list["ComparisonCandidate"]] = relationship(
        back_populates="comparison", cascade="all, delete-orphan"
    )


class ComparisonCandidate(Base):
    __tablename__ = "comparison_candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    comparison_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("comparisons.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_market_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=False,
    )
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    divergences: Mapped[dict | None] = mapped_column(JSON)

    comparison: Mapped[Comparison] = relationship(back_populates="candidates")
