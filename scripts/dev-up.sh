#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not on PATH." >&2
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  if [[ ! -f "$ROOT/.env.example" ]]; then
    echo "Missing .env.example in repo root." >&2
    exit 1
  fi
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo ""
  echo "Created .env from .env.example"
  echo "Edit .env and set ANTHROPIC_API_KEY and VOYAGE_API_KEY for comparisons and ingest."
  echo ""
fi

echo "Building and starting RuleC (db + migrations + backend + frontend)..."
docker compose up --build -d

HEALTH="http://127.0.0.1:8000/healthz"
echo ""
echo "Waiting for API at ${HEALTH} ..."
deadline=$(( $(date +%s) + 300 ))
until curl -fsS "$HEALTH" >/dev/null 2>&1; do
  if (( $(date +%s) > deadline )); then
    echo "Timed out. Try: docker compose logs -f backend" >&2
    exit 1
  fi
  sleep 2
done
echo "API is up."

echo ""
echo "  Frontend   http://localhost:3000"
echo "  API        http://localhost:8000/docs"
echo "  Health     ${HEALTH}"
echo ""
echo "Stop with: docker compose down"
