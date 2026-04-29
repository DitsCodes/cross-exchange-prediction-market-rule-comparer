"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-29 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.config import get_settings

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    exchange_enum = postgresql.ENUM(
        "polymarket", "kalshi", name="exchange_enum", create_type=False
    )
    market_status_enum = postgresql.ENUM(
        "open", "closed", "resolved", "unknown", name="market_status_enum", create_type=False
    )
    comparison_status_enum = postgresql.ENUM(
        "pending", "running", "done", "error", name="comparison_status_enum", create_type=False
    )
    exchange_enum.create(op.get_bind(), checkfirst=True)
    market_status_enum.create(op.get_bind(), checkfirst=True)
    comparison_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "markets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exchange", exchange_enum, nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("slug_or_ticker", sa.String(512), nullable=False),
        sa.Column("url", sa.String(1024)),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("description_raw", sa.Text()),
        sa.Column("rules_raw", sa.JSON()),
        sa.Column("resolution_source", sa.String(512)),
        sa.Column("expiration_ts", sa.DateTime(timezone=True)),
        sa.Column("status", market_status_enum, nullable=False, server_default="unknown"),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("exchange", "external_id", name="uq_markets_exchange_external_id"),
    )
    op.create_index("ix_markets_status", "markets", ["status"])

    settings = get_settings()
    op.create_table(
        "market_embeddings",
        sa.Column(
            "market_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("markets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("embedding", Vector(settings.voyage_dim), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        "CREATE INDEX ix_market_embeddings_vec_cosine "
        "ON market_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_table(
        "comparisons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("input_url", sa.String(1024), nullable=False),
        sa.Column(
            "input_market_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("markets.id", ondelete="SET NULL"),
        ),
        sa.Column("status", comparison_status_enum, nullable=False, server_default="pending"),
        sa.Column("risk_matrix", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "comparison_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "comparison_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comparisons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_market_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("markets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("divergences", sa.JSON()),
    )


def downgrade() -> None:
    op.drop_table("comparison_candidates")
    op.drop_table("comparisons")
    op.execute("DROP INDEX IF EXISTS ix_market_embeddings_vec_cosine")
    op.drop_table("market_embeddings")
    op.drop_index("ix_markets_status", table_name="markets")
    op.drop_table("markets")
    op.execute("DROP TYPE IF EXISTS comparison_status_enum")
    op.execute("DROP TYPE IF EXISTS market_status_enum")
    op.execute("DROP TYPE IF EXISTS exchange_enum")
