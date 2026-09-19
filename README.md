# The Lenny Growth Assistant

A RAG-powered assistant that answers product and growth questions using grounded,
cited answers pulled from real Lenny's Podcast transcripts — plus two dedicated
skills that turn a grounded answer into a Ship 30 for 30 essay or a self-contained
HTML one-pager.

> **Status:** RAG pipeline, session persistence, the React frontend, the agent
> routing layer (Claude Agent SDK), the Ship 30 essay and HTML artifact skills,
> Ollama→OpenAI fallback with a provider toggle, Docker Compose packaging, and
> an automated pytest suite are all implemented and verified. `docker compose
> up --build` has been run end-to-end on a fresh database: all three services
> (db/backend/frontend) start healthy, the backend auto-creates its schema
> *including* the HNSW vector index with zero manual steps, the backend
> reaches host-run Ollama via `host.docker.internal`, and a real chat request
> round-trips correctly through the containerized stack.
>
> **Known limitation:** the OpenAI cloud-fallback integration is code-complete
> and was verified reaching OpenAI's real API (a forced Ollama failure
> correctly triggered the fallback and hit OpenAI's servers) — but the
> configured OpenAI account currently has zero credits, so it has not
> produced a real successful cloud-generated answer end-to-end. This does
> not affect the mandatory local Ollama demo path, which is unaffected and
> fully verified. Fixing this requires adding credits to that account, which
> is out of scope for this engagement.

---

## Architecture Overview

See [`docs/architecture.md`](docs/architecture.md) for the full architecture
and implementation details, [`docs/PRD.md`](docs/PRD.md) for product
scope, assumptions, and trade-offs, and
[`FINAL_REQUIREMENTS_AUDIT.md`](FINAL_REQUIREMENTS_AUDIT.md) for a
requirement-by-requirement audit with the evidence behind each verdict.

Short version:

```text
React / Vite Frontend
        |
        v
FastAPI Backend
        |
        +---------------------+---------------------+
        |                     |                      |
        v                     v                      v
Session API            Chat / Essay /          Agent layer
                        Artifact API          (Claude Agent SDK,
                             |                  intent routing only)
                             v
                    Transcript Retriever
                    (pgvector cosine search
                     + relevance floor)
                             |
                             v
                    PostgreSQL + pgvector
                             |
                             v
                    Grounded LLM Generation
                    (app/llm/router.py)
                             |
                    +--------+--------+
                    v                 v
                 Ollama            OpenAI
              (local, default)    (fallback)
```

---

## Evaluator FAQ

Quick answers to the questions an evaluator setting this up cold is likely
to have. Every claim below is backed by a section further down this README
or in `docs/architecture.md`.

**What do I need to install?**
Python 3.11+, Node.js 20+, and Ollama (with a model pulled) — always.
Docker Desktop if using Option A. Nothing else is required to install
manually: PostgreSQL/pgvector comes from Docker or a managed provider
(Supabase/Railway), and the Claude Agent SDK's CLI is bundled inside its
pip package (see next question).

**Do I need to separately install the Claude Code CLI or run `npm install
-g @anthropic-ai/claude-code`?**
No. `backend/requirements.txt` pins `claude-agent-sdk==0.2.156`, and that
pip package bundles the Claude Code CLI binary it needs for
Windows/Linux/macOS inside the wheel itself. `pip install -r
requirements.txt` is the only install step. See "Agent SDK routing" below.

**Which environment variables are required, and which are optional?**
Only `DATABASE_URL` is required (a reachable Postgres with pgvector). Every
other variable in `backend/.env.example` — `OLLAMA_*`, `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `AGENT_SDK_ENABLED`, `FORCE_LLM_PROVIDER`,
`RAG_MIN_SIMILARITY`, `CORS_ORIGINS` — is optional and has a documented
default or degrades gracefully when absent. See "Key environment variables"
below.

**Is an Anthropic API key required?**
No. It's optional. It only enables the Agent SDK's cloud-based intent
routing; when absent (or `AGENT_SDK_ENABLED=false`), routing falls back
automatically to a local deterministic keyword classifier with zero loss of
core functionality — chat/essay/HTML-artifact generation is entirely
unaffected either way, since the Agent SDK never writes answers, only
classifies intent.

**Is an OpenAI API key required?**
No. It's optional cloud fallback for when Ollama is unreachable or fails.
Leave it blank to run fully offline (requests fail only if Ollama also
fails).

**Is Ollama required?**
Yes — this is the one mandatory dependency. The assignment requires a
working local-model demo with no cloud dependency, and Ollama is that path.
See "Verifying the Ollama-only (fully offline) path" below.

**How does the Agent SDK routing actually work?**
`app/agent/orchestrator.py` uses the Claude Agent SDK for exactly one job:
classifying a chat message's intent (chat / essay / html_artifact) and
optionally checking the knowledge base first via a narrow, read-only MCP
tool. It never generates the final answer — that always flows through
`app/llm/router.py` (Ollama-first, OpenAI-fallback), unchanged regardless of
which router made the classification. Full detail, including the
`permission_mode="dontAsk"` security choice, is in
`docs/architecture.md`'s "Agent layer" section.

**How do I run it in Docker?**
`docker compose up --build` from the repo root (with `ollama serve` already
running on the host). See "Option A: Docker Compose" below.

**How do I run the mandatory Ollama-only demo?**
Unset/omit `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` (or set
`AGENT_SDK_ENABLED=false`), start the app, and confirm `"provider": "ollama"`
in every response. See "Verifying the Ollama-only (fully offline) path"
below.

**How do I run the tests?**
`cd backend && pip install -r requirements-dev.txt && pytest tests -v`. See
"Running tests" below for the DB-dependent-tier details.

**What happens if `ANTHROPIC_API_KEY` is missing or invalid?**
Routing degrades to the local heuristic classifier; the rest of the request
(retrieval, generation, response) proceeds normally. `used_agent_sdk: false`
and `router_error` (non-null) are visible in the response/logs.

**What happens if Ollama is down?**
`generate_with_fallback` catches the failure and retries against OpenAI
(if `OPENAI_API_KEY` is set); `/api/health` reports `"ollama": {"status":
"..."}` independently so this is diagnosable at a glance. If OpenAI is also
unavailable, the request fails with a `502` and an actionable message
rather than a raw stack trace.

**What happens on an empty/no-match retrieval result?**
If no transcript chunk clears `RAG_MIN_SIMILARITY` (default 0.30), the app
returns a fixed "not grounded" message **with no LLM call at all** —
grounding is a structural property of the pipeline, not something the model
is merely asked to self-report. See "Ingestion → retrieval flow" in
`docs/architecture.md`.

**What happens if the database is down?**
The backend fails to start at all (`ensure_schema()` runs at import time),
which is a deliberate fail-fast choice — a degraded-but-running app with no
persistence would be more confusing than a clear startup failure. Once
running, a DB connection lost mid-request returns a `502` with an
actionable message.

**What happens on an LLM timeout?**
`OLLAMA_TIMEOUT_SECONDS` (default 180, sized from measured live latency —
see `.env.example`) bounds the Ollama call; on timeout it's treated the same
as any other Ollama failure and retried against OpenAI per the fallback
logic above.

---

## Prerequisites

- **Python 3.11+** (this repo's venv was built and tested on 3.11/3.14; if you
  hit binary-extension import errors on Windows with a very new Python
  version, see Troubleshooting below)
- **Node.js 20+** and npm
- **Ollama** (https://ollama.com) with a model pulled, e.g.:
  ```
  ollama pull llama3.2:3b
  ollama serve
  ```
- **A Postgres database with the pgvector extension** — either:
  - Docker (for `docker compose up`, which provisions this for you), or
  - A managed Postgres with pgvector already available (e.g. Supabase)
- Optional: an **OpenAI API key** for cloud fallback, and an **Anthropic API
  key** if you want the agent routing layer to use the real Claude Agent SDK
  instead of its offline heuristic fallback. No separate `npm install -g
  @anthropic-ai/claude-code` step is needed — the `claude-agent-sdk` pip
  package (already in `backend/requirements.txt`) bundles the Claude Code CLI
  binary it needs for Windows/Linux/macOS. See "Agent SDK routing" below.

---

## Option A: Docker Compose (recommended)

```bash
# 1. Make sure Ollama is running on the host and has a model pulled:
ollama pull llama3.2:3b
ollama serve

# 2. From the repo root:
docker compose up --build
```

This starts three services:
- `db` — `pgvector/pgvector:pg16`, with schema created automatically on
  backend startup (no manual migration step)
- `backend` — FastAPI on `http://localhost:8000`, connecting to `db` and to
  the host's Ollama via `http://host.docker.internal:11434`
- `frontend` — the built React app served by nginx on `http://localhost:5173`

Override defaults with environment variables before `docker compose up`, e.g.:

```bash
OPENAI_API_KEY=sk-... AGENT_SDK_ENABLED=true ANTHROPIC_API_KEY=sk-ant-... docker compose up --build
```

You still need to ingest the transcripts into the `db` service once — see
"Ingest the transcripts" below, pointing `DATABASE_URL` at
`postgresql://postgres:postgres@localhost:5432/lenny` (the compose service's
published port).

---

## Option B: Manual setup (no Docker)

### 1. Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # then fill in DATABASE_URL at minimum
```

Fill in `.env` — at minimum `DATABASE_URL` pointing at a Postgres instance
with pgvector available. See `.env.example` for every variable and what it
does.

Start the backend:

```bash
uvicorn app.main:app --reload
```

On first run, `ensure_schema()` creates the `vector`/`pgcrypto` extensions,
every table, and the HNSW vector index automatically — no separate migration
step needed. (If your
DB role can't run `CREATE EXTENSION`, e.g. some managed Postgres plans,
enable `vector` and `pgcrypto` yourself first; see
`backend/scripts/setup_db.sql`.)

### 2. Ingest the transcripts

The transcript archive lives in `lennys-podcast-transcripts/episodes/` at the
repo root. With `DATABASE_URL` set (in `.env` or the shell) and the backend's
venv active:

```bash
cd backend
python scripts/ingest.py
```

This chunks each transcript into ~3000-character groups of whole speaker
turns (never splitting mid-sentence), recording each chunk's real timestamp
and speaker from the transcript's own `Speaker (HH:MM:SS):` markers where
present (301/303 files; the rest fall back to a plain character-based
split with no timestamp), embeds each chunk locally with `all-MiniLM-L6-v2`
(no API cost), and inserts into `transcript_chunks`. Safe to re-run: episodes that already have chunks
stored are skipped (by episode title), so re-running after adding new
transcript files only ingests what's new, without duplicating existing
chunks. Pass `--force` to re-embed and replace chunks for episodes that
already exist (e.g. after a chunking/embedding change) instead of skipping
them:

```bash
python scripts/ingest.py --force
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env   # if present; otherwise set VITE_API_URL as below
npm run dev
```

By default the frontend expects the backend at `http://127.0.0.1:8000`. To
point it elsewhere, set `VITE_API_URL` (e.g. in `frontend/.env`):

```
VITE_API_URL=http://127.0.0.1:8000
```

Open `http://localhost:5173`.

---

## Running tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests -v
```

Two tiers of tests:
- **Pure-Python / mocked-boundary tests** (`test_sanitizer.py`,
  `test_router_fallback.py`, `test_orchestrator_routing.py`,
  `test_retriever_threshold.py`, `test_schemas.py`) — no database, no
  network. These always run.
- **API-level tests** (`test_api_*.py`) exercise the real FastAPI app against
  a real Postgres+pgvector database (SQLite can't represent this schema's
  `UUID`/`JSONB`/pgvector `Vector` columns). They need a reachable test
  database:
  ```bash
  docker compose up -d db
  # from repo root, or point TEST_DATABASE_URL at any disposable Postgres+pgvector instance
  TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/lenny pytest backend/tests -v
  ```
  **Do not point `TEST_DATABASE_URL` at a database with real data you want to
  keep** — the test fixtures delete all rows from every table after each
  test. Use a disposable/local database only.

  If no test database is reachable, these tests are skipped individually
  with a clear reason, rather than failing the whole suite.

---

## Verifying the Ollama-only (fully offline) path

The assignment requires a working local-model demo with no cloud dependency.
To verify:

```bash
# In the shell running the backend, make sure no cloud keys are set:
unset OPENAI_API_KEY
unset ANTHROPIC_API_KEY
# or set AGENT_SDK_ENABLED=false in .env to skip the agent SDK attempt entirely
```

Then hit `/api/chat`, `/api/essay`, and `/api/artifact` and confirm
`"provider": "ollama"` in each response, and check `/api/health` shows
`"ollama": {"status": "ok"}`.

---

## Key environment variables

See `backend/.env.example` for the full list with explanations. The most
relevant:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (pgvector required) |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Local model config (mandatory path) |
| `OLLAMA_TIMEOUT_SECONDS` | Ollama request timeout (default `180`; on CPU-only reference hardware, chat/essay/HTML-artifact generation measured 64s/78-105s/121s+ respectively) |
| `OPENAI_API_KEY` | Cloud fallback; blank = fully offline (fails if Ollama also fails) |
| `FORCE_LLM_PROVIDER` | Deployment-wide provider override (`openai` or blank) |
| `RAG_MIN_SIMILARITY` | Cosine-similarity floor for "grounded" (default `0.30`) |
| `AGENT_SDK_ENABLED` | Enable/disable the Claude Agent SDK routing attempt |
| `ANTHROPIC_API_KEY` | Required only if `AGENT_SDK_ENABLED=true` |
| `CORS_ORIGINS` | Extra allowed frontend origins beyond localhost dev ports |

The frontend also has a **provider toggle** in the header (Auto / Ollama /
OpenAI) that overrides the backend default on a per-request basis, without
needing to restart the backend.

---

## Troubleshooting

- **`ImportError: DLL load failed` for numpy/torch/scipy on Windows**: this
  usually means a corrupted or partial package install (seen in this repo's
  own venv during development — a `pip install --force-reinstall
  --no-cache-dir <package>`, or deleting and recreating the venv entirely,
  resolved it). If your project folder is inside a cloud-synced directory
  (OneDrive, Dropbox), also confirm the venv isn't sitting in a
  partially-synced state.
- **Backend crashes on startup with a DB connection error**: confirm
  `DATABASE_URL` is reachable and points at a database with pgvector
  available; `ensure_schema()` runs at import time, so the app won't start at
  all without a reachable DB.
- **`/api/chat` returns "I don't have enough grounded material..." for
  everything**: confirm you ran the ingestion step (`python
  scripts/ingest.py`) against the same database `DATABASE_URL` points at.
- **Ollama responses are slow or time out**: try a smaller model
  (`llama3.2:3b` is the default for a reason), and confirm `ollama serve` is
  running and the model is already pulled (`ollama pull <model>`) so the
  first request isn't also a model download.
- **Docker backend can't reach Ollama**: `host.docker.internal` works out of
  the box with Docker Desktop (Windows/Mac). On native Linux Docker, the
  `extra_hosts: host.docker.internal:host-gateway` entry in
  `docker-compose.yml` handles this, but confirm `ollama serve` is bound to
  more than just `127.0.0.1` if issues persist.
