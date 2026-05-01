"""drop embeddings table and pgvector extension

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-01 00:00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_market_embeddings_vec_cosine")
    op.execute("DROP TABLE IF EXISTS market_embeddings")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_markets_title_trgm "
        "ON markets USING gin (title gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_markets_title_trgm")
