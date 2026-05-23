# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A LangGraph-based multi-agent supply-chain platform. A `SupervisorAgent` plans, routes, and aggregates results from five specialist agents (`data_analyst`, `risk_agent`, `finance_agent`, `meeting_agent`, `email_agent`). Persistence is PostgreSQL via SQLAlchemy plus ChromaDB for vector search. Optional observability via Comet/Opik.

The repo is a fork of `Bhardwaj-Saurabh/OmniSupply-...`. The upstream is missing `src/data/` (see the gap below).

## Critical gap: `src/data/` was missing on clone

`.gitignore` had a bare `data/` pattern that matched both the top-level `data/` (CSV folder, correctly ignored) AND `src/data/` (application code, incorrectly ignored). Result: `src/data/models.py`, `src/data/ingestion/loaders.py`, and `src/data/ingestion/validators.py` were never committed in upstream or this fork. Without them, `database.py` and every agent fail to import.

Fixed on 2026-05-23 in this fork:
- `.gitignore` line for data tightened from `data/` to `/data/` (root-relative only).
- `src/data/models.py` reconstructed from `src/storage/sql/models.py` (Pydantic mirrors of the SQLAlchemy ORM models, plus `AgentResult` and a `RiskAssessment` placeholder).
- `src/data/ingestion/{loaders,validators}.py` written as stubs (raise `NotImplementedError`). Only `omnisupply_demo.py` calls them — the Streamlit deploy doesn't need them. Fill in if you want the demo's CSV ingestion to actually work.

If you ever need to do this kind of reconstruction again: the source of truth for the Pydantic field names is the kwargs passed to `DatabaseClient.insert_orders/insert_shipments/insert_inventory/insert_transactions` in `src/storage/sql/database.py`.

## Setup and execution

```bash
uv sync                    # builds .venv from pyproject.toml + uv.lock
cp .env.example .env       # then edit with real values
.venv/bin/streamlit run app.py        # web GUI on http://localhost:8501
.venv/bin/python omnisupply_demo.py   # CLI demo; needs CSV ingestion implemented
```

`uv` is the canonical installer here — `uv.lock` is ~1 MB of pinned resolution. `pip install -e .` works too but ignores the lock. `requirements.txt` exists but is out of date; prefer `pyproject.toml`.

Python 3.11 is required (pinned in `.python-version` + `pyproject.toml`). Several deps (e.g. `psycopg2-binary`, `langchain-openai`) have wheels for 3.11; newer Python may pull source builds and need system libs.

## Required vs optional services

| Service | Required? | Where it's used | Env vars |
|---|---|---|---|
| OpenAI | yes | every agent + supervisor | `OPENAI_API_KEY` (+ `OPENAI_MODEL`) |
| PostgreSQL | yes | `DatabaseClient` explicitly rejects non-postgres URLs | `DATABASE_URL` |
| ChromaDB | yes | `OmniSupplyVectorStore` — runs embedded, no external service | — |
| Comet / Opik | optional | `OpikTracer` callbacks + `@track` decorators | `COMET_API_KEY`, `COMET_WORKSPACE`, `OPIK_PROJECT_NAME` |
| Redis | optional | only Celery scheduler (daily reports, periodic risk checks) | `REDIS_URL` |
| SMTP | optional | `email_agent` actual delivery (otherwise it just drafts) | `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` |

When Comet is not configured, `OpikTracer` prints a warning at instantiation but the agents still run — confirmed via smoke test on 2026-05-23.

## Architecture

### Supervisor workflow (`src/supervisor/orchestrator.py`)

LangGraph `StateGraph` with six sequential nodes, all driven by `SupervisorAgent.execute(query)`:

1. `parse_query` — adds timestamp + available-agents to context.
2. `plan_task` — LLM produces a `TaskPlan` (steps, agents_needed, expected_output).
3. `select_agents` — LLM produces an `AgentSelection` (agent list + `parallel` vs `sequential` flag). Falls back to `AgentRegistry.find_best_agent` if no valid agents picked.
4. `execute_agents` — runs selected agents either in parallel (`asyncio.to_thread`) or sequentially (passing each result into the next agent's context).
5. `aggregate_results` — collates insights, recommendations, metrics into `state['context']`.
6. `generate_report` — LLM produces an `ExecutiveSummary` (summary, key_insights, recommendations, kpis), and `_build_report` turns it into a markdown document stored in `state['final_report']`.

Return value of `execute()`: a dict with `final_report`, `executive_summary`, `agent_results`, `selected_agents`, `task_plan`, `error`.

### Agents (`src/agents/`)

All five inherit `BaseAgent` (`src/agents/base.py`). Each implements:
- `_build_graph()` → a LangGraph workflow specific to that agent
- `get_capabilities()` → list of strings used both for routing and the Streamlit sidebar
- `_format_result(state)` → converts the final agent state to an `AgentResult`

`BaseAgent.execute(query, context)` runs the graph, times it, wraps exceptions into a failed `AgentResult` so the supervisor never crashes on a single bad agent. The `@track(project_name=...)` decorator on `execute` is what Opik logs.

`AgentRegistry` is a simple `Dict[str, BaseAgent]` with `register/get_agent/list_agents/find_best_agent`. The supervisor takes a registry, not individual agents.

### Storage

- `src/storage/sql/database.py` — `DatabaseClient`. Postgres-only (rejects other URLs at init). Creates a custom schema named `omnisupply` with `AUTHORIZATION <db_user>`, sets `search_path` to that schema, and runs `Base.metadata.create_all`. Insert methods take lists of Pydantic models (from `src/data/models.py`) and bulk-save with SQLAlchemy.
- `src/storage/sql/models.py` — SQLAlchemy ORM. Includes `OrderDB`, `ShipmentDB`, `InventoryDB`, `FinancialTransactionDB`, plus `AgentExecutionLog`, `ReportArchive`, `AlertLog`.
- `src/storage/vector/chromadb_client.py` — embedded ChromaDB, persistence at `settings.CHROMA_DIR` (default `data/chroma/`).

### Configuration

`config/settings.py` defines `Settings` (pydantic-settings). Read-only. Most other modules read env vars directly via `os.getenv` instead of going through `settings`, so changing a default here doesn't always propagate.

## Streamlit GUI + Railway deployment

`app.py` (repo root) wraps `SupervisorAgent.execute()` in a Streamlit UI:
- Sidebar shows OpenAI/Opik/Postgres health, registered agents and their capabilities, and clickable example queries.
- Main panel: text-area query input → spinner → task plan + per-agent result cards + executive summary + downloadable markdown report.
- `build_platform()` is `@st.cache_resource` so DB/vector/agents are constructed once per session.
- Defensive: if `DATABASE_URL` is unset or the DB is unreachable, agents are still created with `db_client=None`. The platform loads; individual agent results will surface the missing-DB errors.

Deployment recipe (matches `~/InvAgent`, `~/TradingAgents`):
- `Dockerfile` — `python:3.11-slim`, installs `gcc g++ git curl libpq-dev`, installs `uv`, two-stage `uv sync` (deps first for layer cache, then project), `CMD .venv/bin/streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true`.
- `railway.toml` — `DOCKERFILE` builder, 300s healthcheck, `ON_FAILURE` × 3 restart.
- `.env.example` — only placeholders. Real keys go in Railway's Variables tab. `DATABASE_URL` and `REDIS_URL` are auto-injected when you attach the Railway Postgres / Redis plugins.
- `.dockerignore` — excludes `data/`, `notebooks/`, the heavy `*.md` docs, `.venv`, caches, `.env`, `.claude/`.

The Postgres plugin is required for the deploy to be useful; without it `DATABASE_URL` is empty and every agent that needs data fails. The Redis plugin is only needed if you turn on Celery scheduling — Streamlit on its own doesn't.

## Things that will trip you up

- **Don't add a bare directory name to `.gitignore`** if the same name also appears under `src/`. Use `/data/` (root-anchored), not `data/`.
- **`omnisupply_demo.py` and `app.py` disagree about Postgres config.** The demo builds `DATABASE_URL` from `POSTGRES_USER/PASSWORD/DB/HOST/PORT`; the database client and `app.py` read `DATABASE_URL` directly. Set `DATABASE_URL` and you cover both paths.
- **`requirements.txt` is stale.** `pyproject.toml` + `uv.lock` is the source of truth.
- **Empty DB ≠ broken deploy.** The Streamlit app and supervisor both work against an empty Postgres. Agents will return `success=False` for data-dependent queries, but the surface is fine for verifying the deploy itself.
