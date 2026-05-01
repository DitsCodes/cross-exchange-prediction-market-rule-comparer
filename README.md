# RuleC — Cross-Platform Prediction Market Rules Comparer

Paste a Polymarket or Kalshi URL. RuleC fetches the market via API, retrieves
similar markets on the *opposite* exchange via Postgres trigram lexical search,
and uses Anthropic Claude to generate a **Structural Risk Matrix** highlighting
divergences in resolution sources, dead-heat tie-breaking rules, and expiration
timestamps so you can spot potential settlement-divergence risk and arbitrage
windows.

```
        ┌────────────┐  POST /compare   ┌──────────────────┐
 user → │  Next.js   │ ───────────────▶ │     FastAPI      │
        └────────────┘   SSE stream     └────────┬─────────┘
                                                 │
                            ┌────────────────────┴──────────────────────┐
                            │           LangGraph supervisor            │
                            │  fetcher → retriever → extractor → risk   │
                            └──────┬───────┬──────────┬─────────────────┘
                                   │       │          │
                                   ▼       ▼          ▼
                            Polymarket   Postgres    Anthropic Claude
                            Kalshi      (pg_trgm)
```

## Stack

| Layer        | Choice                                                        |
| ------------ | ------------------------------------------------------------- |
| Backend      | FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic                |
| Storage      | Postgres 16 with `pg_trgm` (GIN trigram index on title)       |
| Agents       | LangGraph `StateGraph` over `langchain-anthropic` (Claude)    |
| Similarity   | Postgres `similarity()` (pg_trgm) — no embedding API required |
| Scheduling   | APScheduler in-process job (open-market catalog refresh)      |
| Frontend     | Next.js 15 (App Router) + Tailwind CSS                        |
| Streaming    | Server-Sent Events via `sse-starlette`                        |

## Quick start (Docker, recommended)

**One command (creates `.env` from `.env.example` if missing, starts Postgres, runs Alembic migrations, then API + frontend):**

| OS      | Command |
| ------- | ------- |
| Windows | `powershell -ExecutionPolicy Bypass -File scripts/dev-up.ps1` |
| macOS/Linux | `bash scripts/dev-up.sh` |

Manual equivalent:

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY (the only API key required)
docker compose up --build
```

- API:      http://localhost:8000  (`/healthz`, `/docs`)
- Frontend: http://localhost:3000

The first compose run performs `alembic upgrade head` automatically. Postgres
creates the `rulec` database on first startup; no manual DB creation is required.
The `pg_trgm` extension is enabled by migration so the lexical retriever works
out of the box. To bootstrap the catalog manually instead of waiting for the
scheduler:

```bash
curl -X POST http://localhost:8000/admin/ingest \
  -H "x-admin-token: $ADMIN_TOKEN"
```

## Local dev

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## API

| Method | Path                              | Notes                                         |
| ------ | --------------------------------- | --------------------------------------------- |
| POST   | `/api/v1/compare`                 | `{ "url": "..." }` → `{ comparison_id }`      |
| GET    | `/api/v1/compare/{id}`            | Latest status + risk matrix                   |
| GET    | `/api/v1/compare/{id}/stream`     | SSE: `started`, `step`, `result`, `error`     |
| GET    | `/api/v1/markets/{exch}/{ident}`  | Debug: fetch a single market                  |
| POST   | `/admin/ingest`                   | Trigger catalog refresh (`x-admin-token`)     |
| GET    | `/healthz`                        | Health probe                                  |

## Risk Matrix output

```jsonc
{
  "input": { "exchange": "polymarket", "title": "...", "url": "...",
             "rules": { "resolution_source_primary": "...", "tiebreak_rule": "...",
                        "expiration_ts_utc": "2026-11-04T05:00:00Z" } },
  "rows": [{
    "candidate": { "exchange": "kalshi", "title": "...", "similarity": 0.42 },
    "dimensions": {
      "resolution_source": { "input": "...", "candidate": "...", "divergence": "high",   "note": "..." },
      "tiebreak":          { "input": "...", "candidate": "...", "divergence": "high",   "note": "..." },
      "expiration":        { "input": "...", "candidate": "...", "divergence": "medium", "note": "19h gap" },
      "scope":             { "input": "...", "candidate": "...", "divergence": "low",    "note": "..." }
    },
    "arbitrage_flag": "potential",
    "rationale": "Kalshi may settle ~19h later on a different source..."
  }]
}
```

`similarity` is a pg_trgm score in `[0, 1]` — typically `0.2–0.6` for closely
related cross-exchange titles. It is *not* directly comparable to a cosine
embedding score.

## How the agents are wired

`app/agents/supervisor.py` compiles a LangGraph `StateGraph` with four nodes:

1. **MarketFetcher** (`market_fetcher.py`) — detects exchange, parses URL, calls
   the exchange API, persists the input market.
2. **SimilarityRetriever** (`similarity_retriever.py`) — runs Postgres
   `similarity(title, $input_title)` (pg_trgm) restricted to the opposite
   exchange, returns top-K candidates above the similarity floor. No external
   embedding API.
3. **RulesExtractor** (`rules_extractor.py`) — Claude extracts a strict
   `ExtractedRules` JSON schema for the input + every candidate. Falls back to a
   safe heuristic when no `ANTHROPIC_API_KEY` is configured.
4. **RiskSynthesizer** (`risk_synthesizer.py`) — runs deterministic per-dimension
   diffs (resolution source jaccard, tiebreak classification, expiration
   timedelta, scope similarity), wrapped by a Claude call that produces the
   one-line `rationale` and `arbitrage_flag`.

State flows through a shared `CompareState` `TypedDict` defined in
`app/agents/state.py`. The supervisor halts cleanly with errors recorded in
`state["errors"]` if any node fails.

## Data model

| Table                    | Purpose                                                    |
| ------------------------ | ---------------------------------------------------------- |
| `markets`                | Canonical normalized markets, unique on `(exchange, ext)`, GIN trigram index on `title` |
| `comparisons`            | One row per compare run, JSON `risk_matrix`               |
| `comparison_candidates`  | Per-candidate divergences for analytics                   |

## Tests

```bash
cd backend && pytest -q
```

The suite covers:
- URL parsing for both exchanges
- API normalization with `respx` mocked Polymarket/Kalshi responses
- The lexical retriever's filtering and diagnostics
- The deterministic per-dimension diff scorer
- An end-to-end synthesizer node test in heuristic mode (no LLM)

## Notes

- Output is **advisory**. Always read the original market rules.
- Catalog is bounded to currently-open markets.
- Anthropic Claude is the only external API key required.
- The compare API has a soft 60/min IP rate limit (`slowapi`).
