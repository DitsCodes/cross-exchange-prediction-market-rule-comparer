# RuleC — Agent Handoff

This document orients future coding agents on **RuleC** (Cross-Platform Prediction Market Rules Comparer). Read this before making changes. For a shorter snapshot, see [`CLAUDE.md`](./CLAUDE.md) and [`README.md`](./README.md).

---

## What this project does

RuleC compares settlement rules across **Polymarket** and **Kalshi**. A user pastes a market URL from either exchange. The backend:

1. Fetches and normalizes the input market from the exchange API.
2. Finds similar markets on the **opposite** exchange via Postgres **trigram** (`pg_trgm`) title search.
3. Uses **Anthropic Claude** to extract structured rule fields.
4. Scores deterministic per-dimension divergences and produces a **Structural Risk Matrix** with arbitrage flags.

Output is **advisory** — it highlights potential settlement-divergence risk, not trading advice.

---

## Stack at a glance

| Layer | Technology |
| --- | --- |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| Agents | LangGraph `StateGraph`, `langchain-anthropic` |
| Database | Postgres 16, `pg_trgm` (GIN index on `markets.title`) |
| Scheduling | APScheduler (in-process catalog ingest) |
| Frontend | Next.js 15 App Router, Tailwind CSS, TypeScript strict |
| Streaming | SSE via `sse-starlette` |
| Rate limiting | `slowapi` (60 req/min per IP) |

**External APIs required:** Anthropic Claude only. Polymarket Gamma and Kalshi v2 are public HTTP APIs (no keys). **No embedding provider** — similarity is lexical via `pg_trgm`.

---

## Repository layout

```
cross-exchange-prediction-market-rule-comparer/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, rate limit, lifespan
│   │   ├── config.py            # pydantic-settings from .env
│   │   ├── api/v1/              # compare, markets, health, admin routes
│   │   ├── agents/              # LangGraph nodes + supervisor
│   │   ├── exchanges/           # Polymarket + Kalshi adapters
│   │   ├── services/            # compare_service, catalog_ingester
│   │   ├── db/                  # SQLAlchemy models + engine
│   │   └── schemas/market.py    # Pydantic types shared across layers
│   ├── alembic/                 # DB migrations
│   ├── tests/                   # pytest suite (respx mocks for HTTP)
│   └── scripts/live_smoke.py    # Manual live E2E (not pytest)
├── frontend/
│   ├── app/                     # pages: /, /compare/[id]
│   ├── components/              # UrlInput, RiskMatrix, AgentTimeline, etc.
│   └── lib/                     # api.ts, types.ts
├── scripts/dev-up.sh            # Docker bootstrap (macOS/Linux)
├── scripts/dev-up.ps1           # Docker bootstrap (Windows)
├── docker-compose.yml
├── .env.example
├── CLAUDE.md                    # Short agent context
└── HANDOFF.md                   # This file
```

---

## How to run locally

### Docker (recommended)

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env
bash scripts/dev-up.sh          # or scripts/dev-up.ps1 on Windows
# OR: docker compose up --build
```

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/healthz

Compose starts Postgres → runs `alembic upgrade head` → starts backend → starts frontend.

### Backend only

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend only

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE=http://localhost:8000` in `frontend/.env.local` if the API is not on localhost:8000.

### Bootstrap the market catalog

Similarity search requires ingested markets on the **opposite** exchange. By default `INGEST_ON_STARTUP=false`.

```bash
curl -X POST http://localhost:8000/admin/ingest \
  -H "x-admin-token: $ADMIN_TOKEN"
```

Without catalog data, the retriever returns zero candidates with diagnostic hints in SSE events.

---

## End-to-end compare flow

```
User URL
   │
   ▼
POST /api/v1/compare  ──► create_comparison() ──► background run_comparison()
   │                         (comparisons row: pending)
   ▼
Frontend navigates to /compare/{id}
   │
   ├── GET /api/v1/compare/{id}     (poll status + result)
   └── GET /api/v1/compare/{id}/stream  (SSE: started, step, result, error)
```

### LangGraph pipeline (`backend/app/agents/supervisor.py`)

Linear graph with conditional early exits:

```
fetcher ──► retriever ──► extractor ──► synthesizer ──► END
   │            │
   halt         halt (no candidates)
```

| Node | File | Responsibility |
| --- | --- | --- |
| **fetcher** | `market_fetcher.py` | `detect_exchange()` → parse URL → exchange API → upsert input to `markets` |
| **retriever** | `similarity_retriever.py` | `similarity(title, $input_title)` on opposite exchange, filter by `SIMILARITY_MIN_SCORE`, top-K |
| **extractor** | `rules_extractor.py` | Claude extracts `ExtractedRules` JSON for input + each candidate; heuristic fallback without API key |
| **synthesizer** | `risk_synthesizer.py` | Deterministic diffs (resolution, tiebreak, expiration, scope) + Claude/heuristic rationale |

Shared state: `CompareState` in `backend/app/agents/state.py`.

Final payload shape: `build_risk_matrix_payload()` in `risk_synthesizer.py` → stored in `comparisons.risk_matrix` JSON.

---

## Key backend modules

### Configuration (`backend/app/config.py`)

All settings come from `.env` via `pydantic-settings`. Important knobs:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | (empty) | Required for LLM extraction/rationale; empty → heuristic mode |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5` | Claude model |
| `SIMILARITY_TOP_K` | `8` | Max candidates returned |
| `SIMILARITY_MIN_SCORE` | `0.18` | pg_trgm floor (lower than cosine; 0.2–0.6 is typical for good matches) |
| `INGEST_ON_STARTUP` | `false` | Start APScheduler on app boot |
| `INGEST_INTERVAL_MINUTES` | `30` | Catalog refresh interval |
| `ADMIN_TOKEN` | `change-me` | Header `x-admin-token` for `/admin/ingest` |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated |

### Exchange adapters (`backend/app/exchanges/`)

- **`base.py`**: `MarketSource` ABC, `detect_exchange()`, `get_source()`, URL validation.
- **`polymarket.py`**: Gamma API (`POLYMARKET_BASE`). Parses slugs and condition IDs from URLs.
- **`kalshi.py`**: Kalshi v2 API (`KALSHI_BASE`). Filters MVE parlay markets (`KXMVE` prefix). Builds matchable titles for multi-outcome events by appending `yes_sub_title`.

Both use `httpx` + `tenacity` retries. Implement `parse_url`, `fetch`, `list_open`.

### Compare service (`backend/app/services/compare_service.py`)

Bridges LangGraph to persistence:

- Creates `comparisons` row on POST.
- Updates status: `pending` → `running` → `done` | `error`.
- Persists `comparison_candidates` rows from final matrix.
- `stream_comparison()` yields SSE events while graph runs.

### Catalog ingester (`backend/app/services/catalog_ingester.py`)

- Paginates `list_open()` from both exchanges.
- Batch upserts into `markets` on `(exchange, external_id)` conflict.
- APScheduler job when `ingest_on_startup=true`; otherwise only via `/admin/ingest`.
- Access via `request.app.state.ingester` (initialized in `main.py` lifespan).

### API routes

| Method | Path | Handler |
| --- | --- | --- |
| POST | `/api/v1/compare` | Create comparison, background task |
| GET | `/api/v1/compare/{id}` | Status + risk matrix |
| GET | `/api/v1/compare/{id}/stream` | SSE stream |
| GET | `/api/v1/markets/{exchange}/{identifier}` | Debug single market fetch |
| POST | `/admin/ingest` | Manual catalog refresh |
| GET | `/healthz` | Health probe |

---

## Database schema

Migrations: `backend/alembic/versions/`

| Table | Purpose |
| --- | --- |
| `markets` | Normalized catalog; unique `(exchange, external_id)`; GIN trigram index on `title` |
| `comparisons` | One row per compare run; JSON `risk_matrix`, status enum |
| `comparison_candidates` | Per-candidate divergence JSON for analytics |

**Migration history note:** `0002_drop_embeddings` removed `market_embeddings`, `pgvector`, and Voyage embedding support. Similarity is **pg_trgm only**. Some comments/scripts still reference the old embedding stack (see Stale references below).

Extensions: `pg_trgm` enabled in migration `0001`.

---

## Frontend architecture

### Pages

- **`app/page.tsx`**: Landing + `UrlInput` form.
- **`app/compare/[id]/page.tsx`**: Client component; polls `getCompare()`, opens `EventSource` on `/stream` for live agent steps, renders `AgentTimeline`, `MarketCard`, `RiskMatrix`.

### API client (`frontend/lib/api.ts`)

- `NEXT_PUBLIC_API_BASE` defaults to `http://localhost:8000`.
- Friendly network error if backend is down.

### Types (`frontend/lib/types.ts`)

Mirror backend Pydantic schemas. Keep in sync when changing API response shapes.

### Components

| Component | Role |
| --- | --- |
| `UrlInput` | POST compare → router.push to `/compare/{id}` |
| `AgentTimeline` | Renders SSE step events |
| `RiskMatrix` | Divergence table with badges |
| `MarketCard` | Input market summary |
| `DivergenceBadge` | low/medium/high styling |

---

## Schemas worth knowing

Defined in `backend/app/schemas/market.py`:

- **`NormalizedMarket`**: Canonical market shape for all agents.
- **`ExtractedRules`**: LLM-extracted fields (resolution source, tiebreak, expiration, scope, etc.).
- **`Candidate`**: Retriever output with similarity score.
- **`RiskRow` / `RiskMatrix`**: Final compare output.

Frontend duplicates these in `frontend/lib/types.ts`.

---

## Testing

```bash
cd backend && pytest -q
cd frontend && npm run lint
```

### Backend test files

| File | Covers |
| --- | --- |
| `test_url_edges.py` | URL parsing edge cases |
| `test_polymarket.py` / `test_kalshi.py` | Exchange normalization (respx mocks) |
| `test_similarity_retriever.py` | Retriever filtering + diagnostics |
| `test_risk_synthesizer.py` | Deterministic diff scoring |
| `test_catalog_ingester.py` | Ingest upsert logic |
| `test_api_smoke.py` | FastAPI route smoke |
| `test_supervisor_e2e.py` | Graph E2E with mocked DB |

Tests set `ANTHROPIC_API_KEY=""` in `conftest.py` to force heuristic LLM fallback.

### Manual live smoke

```bash
cd backend
PYTHONPATH=. python scripts/live_smoke.py "https://polymarket.com/..."
```

Patches DB upsert and retriever; hits real exchange API. Not part of pytest.

---

## Coding conventions

### Backend

- Python 3.11+, Ruff (`line-length = 100`, `py311`).
- SQLAlchemy 2 style (`Mapped`, `mapped_column`).
- Async nodes in LangGraph; DB access via sync `get_session_ctx()` inside nodes.
- Exchange adapters: always `aclose()` httpx clients in `finally` blocks.
- Prefer extending existing patterns over new abstractions.

### Frontend

- TypeScript strict, path alias `@/*`.
- Client components only where needed (`"use client"`).
- Tailwind + CSS variables in `globals.css` (`--accent`, `--border`, etc.).
- Next config: `output: "standalone"` for Docker.

### General agent rules

- **Minimize scope** — focused diffs only.
- **Do not commit `.env`** or secrets.
- **Do not create git commits** unless the user asks.
- Run relevant tests after backend changes.

---

## Common tasks for future agents

### Add a new exchange

1. Create `backend/app/exchanges/<name>.py` implementing `MarketSource`.
2. Add enum value in `db/models.py` `Exchange` + Alembic migration for enum.
3. Wire into `detect_exchange()`, `get_source()`, `all_sources()`.
4. Add URL parsing tests + normalization tests with respx.
5. Update frontend types/examples if user-facing.

### Tune similarity matching

- Adjust `SIMILARITY_MIN_SCORE` in `.env` (start ~0.15–0.25).
- Improve title normalization in exchange adapters (see Kalshi `_build_title`).
- Consider indexing additional text fields (would need migration + retriever change).

### Change risk dimensions

1. Extend `ExtractedRules` schema + LLM prompts in `rules_extractor.py`.
2. Add `_diff_*` function in `risk_synthesizer.py`.
3. Update `RiskRow.dimensions` and frontend `RiskMatrix` component.
4. Add unit tests in `test_risk_synthesizer.py`.

### Add API endpoints

- New router in `backend/app/api/v1/`, register in `main.py`.
- Add Pydantic schemas in `schemas/`.
- Mirror types in `frontend/lib/types.ts` if consumed by UI.

---

## Known stale references (embedding migration)

The project **removed** Voyage embeddings and pgvector (migration `0002`). These files still mention the old stack and may confuse agents:

| Location | Stale content |
| --- | --- |
| `frontend/app/page.tsx` | "Voyage embeddings + pgvector search" in pipeline step 02 |
| `scripts/dev-up.sh` | Mentions `VOYAGE_API_KEY` |
| `scripts/dev-up.ps1` | Mentions pgvector and `VOYAGE_API_KEY` |
| `backend/scripts/live_smoke.py` | Comments refer to "vector retriever" |
| `backend/tests/test_supervisor_e2e.py` | Docstring mentions "embeddings" |

**Source of truth:** README, CLAUDE.md, and `similarity_retriever.py` (pg_trgm only).

---

## Operational gotchas

1. **Empty retriever results** — Usually means catalog not ingested. Run `/admin/ingest` or set `INGEST_ON_STARTUP=true`.
2. **Trigram scores ≠ embedding cosine** — Typical good cross-exchange matches are 0.2–0.6, not 0.8+.
3. **No API key** — App runs in heuristic mode (basic rule extraction, keyword-based rationale). Tests rely on this.
4. **Kalshi MVE parlays** — Filtered at ingest; they pollute open-market listings with comma-joined leg titles.
5. **Compare POST + SSE** — POST kicks off a background task; the stream endpoint re-runs the graph. Both paths exist; frontend uses stream on the compare page.
6. **Rate limit** — 60/min per IP on all routes via slowapi default.
7. **Column length limits** — Ingest truncates strings to fit DB columns (`_fit_column` in ingester).
8. **Docker backend volume** — `./backend:/app` mount enables hot reload in compose.

---

## Environment files

| File | Purpose |
| --- | --- |
| `.env` | Local secrets (gitignored); copy from `.env.example` |
| `.env.example` | Template with all backend + frontend vars |
| `frontend/.env.local` | Optional override for `NEXT_PUBLIC_API_BASE` |

Only **`ANTHROPIC_API_KEY`** is required for full LLM-powered comparisons.

---

## Architecture diagram

```
┌─────────────┐   POST /compare    ┌──────────────────────────────────────────┐
│   Next.js   │ ─────────────────► │              FastAPI (main.py)              │
│  frontend   │ ◄── SSE /stream ── │  compare_service ◄──► comparisons table   │
└─────────────┘                    └──────────────────┬───────────────────────┘
                                                    │
                    ┌───────────────────────────────┴───────────────────────────┐
                    │              LangGraph supervisor (supervisor.py)          │
                    │  fetcher → retriever → extractor → synthesizer             │
                    └─┬─────────┬──────────┬──────────────┬────────────────────┘
                      │         │          │              │
                      ▼         ▼          ▼              ▼
                 Polymarket   Postgres   Anthropic     Deterministic
                 Kalshi API   pg_trgm    Claude        diff + rationale
                              markets
                              catalog
```

---

## Quick reference: file → responsibility

| When you need to… | Start here |
| --- | --- |
| Change compare API contract | `api/v1/compare.py`, `services/compare_service.py` |
| Modify agent pipeline order | `agents/supervisor.py` |
| Fix URL parsing | `exchanges/polymarket.py`, `exchanges/kalshi.py`, `exchanges/base.py` |
| Tune similarity search | `agents/similarity_retriever.py`, `config.py` |
| Change LLM prompts | `agents/rules_extractor.py`, `agents/risk_synthesizer.py` |
| Fix catalog ingest | `services/catalog_ingester.py`, exchange `list_open()` |
| Add DB tables/columns | `db/models.py` + new Alembic revision |
| Update UI for results | `components/RiskMatrix.tsx`, `app/compare/[id]/page.tsx` |
| Debug a single market | `GET /api/v1/markets/{exchange}/{identifier}` |

---

## Related docs

- [`README.md`](./README.md) — User-facing overview, API table, risk matrix example JSON
- [`CLAUDE.md`](./CLAUDE.md) — Condensed project context for agents
- FastAPI auto-docs — http://localhost:8000/docs when running

---

*Last updated: 2026-07-07. Reflects pg_trgm similarity (post-embedding removal).*
