"""Test fixtures."""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://rulec:rulec@localhost:5432/rulec_test")
