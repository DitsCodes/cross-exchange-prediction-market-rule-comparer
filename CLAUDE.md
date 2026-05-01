## Project Context

### Project Snapshot
- **Name:** RuleC
- **Type:** Full-stack web app for cross-exchange prediction market rule comparison
- **Core stack:** FastAPI, LangGraph, SQLAlchemy, Postgres 16 + `pg_trgm`, Next.js 15, Tailwind CSS
- **Primary runtime split:** Python backend + Node/React frontend
- **External APIs:** Anthropic Claude only (no embedding provider)

### Key Commands
- **Windows dev up:** `powershell -ExecutionPolicy Bypass -File scripts/dev-up.ps1`
- **macOS/Linux dev up:** `bash scripts/dev-up.sh`
- **Compose manual start:** `docker compose up --build`
- **Backend local dev:** `cd backend && pip install -e .[dev] && alembic upgrade head && uvicorn app.main:app --reload`
- **Frontend local dev:** `cd frontend && npm install && npm run dev`
- **Backend tests:** `cd backend && pytest -q`
- **Frontend lint:** `cd frontend && npm run lint`

### Directory Overview
- `backend/app/api/v1/` - FastAPI routes (`compare`, `markets`, `admin`, `health`)
- `backend/app/agents/` - LangGraph supervisor and node implementations
- `backend/app/exchanges/` - Exchange adapters (Polymarket, Kalshi)
- `backend/app/services/` - Compare orchestration and catalog ingestion
- `backend/app/db/` - SQLAlchemy models and engine setup
- `backend/alembic/` - Database migrations
- `backend/tests/` - Pytest suite
- `frontend/app/` - Next.js App Router pages and layout
- `frontend/components/` - Reusable UI components
- `frontend/lib/` - API client and shared frontend types
- `scripts/` - Cross-platform startup scripts

### Architecture Notes
- Compare flow is agentic and state-driven: fetch input market, retrieve similar opposite-exchange markets, extract rules, then synthesize structural risk divergence.
- Similarity search uses Postgres `pg_trgm` `similarity(title, $query)` against the opposite exchange's catalog (GIN trigram index on `markets.title`). No embedding provider is used.
- Compare progress streams to the frontend via SSE endpoint.
- Docker Compose handles startup order: DB health check -> backend (with migrations) -> frontend.

### Coding and Ops Conventions
- Backend uses Python 3.11+ with Pydantic v2 and SQLAlchemy 2 style.
- Backend linting/config includes Ruff (`line-length = 100`, `target-version = py311`).
- Frontend uses TypeScript strict mode with Next.js path alias `@/*`.
- Next config uses `output: "standalone"` for container/runtime packaging.
- `.env` is present locally and is gitignored; avoid committing secrets.
