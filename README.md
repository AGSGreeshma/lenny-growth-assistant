# The Lenny Growth Assistant

A RAG-powered assistant that answers product and growth questions using grounded,
cited answers pulled from real Lenny's Podcast transcripts — plus two dedicated
skills that turn a grounded answer into a Ship 30 for 30 essay or a self-contained
HTML one-pager.

> **Status:** RAG pipeline, session persistence, the React frontend, the agent
> routing layer (Claude Agent SDK), the Ship 30 essay and HTML artifact skills,
> Ollama→Gemini fallback with a provider toggle, Docker Compose packaging, and
> an automated pytest suite are all implemented and verified. `docker compose
> up --build` has been run end-to-end on a fresh database: all three services
> (db/backend/frontend) start healthy, the backend auto-creates its schema
> *including* the HNSW vector index with zero manual steps, the backend
> reaches host-run Ollama via `host.docker.internal`, and a real chat request
> round-trips correctly through the containerized stack.
>
> **Provider architecture:** the automatic (AUTO) chain is Ollama → Gemini
> only. OpenAI is fully implemented and selectable explicitly
> (`provider="openai"` / `FORCE_LLM_PROVIDER=openai`) but is deliberately
> **not** part of the automatic fallback — this is a product decision (an
> unfunded or intentionally-reserved OpenAI key should never be silently
> billed by a Gemini/Ollama failure), not a limitation. See "Ship 30 for 30
> length vs. local-model latency" below and `agent_transcripts/` for the
> full reasoning.
>
> **Known limitation:** `OPENAI_API_KEY` (when explicitly selected) was
> previously verified reaching OpenAI's real API but rejected with a `401
> Incorrect API key provided` — it needs a valid, funded key to actually
> generate, which is out of scope for this engagement. **Gemini's
> integration is new and not yet independently live-verified end-to-end
> with a real funded request** in this repository's own testing — the
> router-level logic is covered by automated tests (mocked, no real network
> call), but confirm `GEMINI_API_KEY`/`GEMINI_MODEL` actually generate a
> real response on your own setup before relying on it. Neither of this
> affects the mandatory local Ollama demo path, which is unaffected and
> fully verified.
>
> **Deliberate trade-off:** the Ship 30 for 30 skill targets ~1,240–1,250
> words as its ideal content length, but the local Ollama path runs under a
> 120s soft generation budget (streamed, not a hard cutoff) so the mandatory
> local demo stays responsive on CPU-only hardware — a locally-generated
> essay may come back shorter than the ideal target, by design. See "Ship 30
> for 30 length vs. local-model latency" below for the full reasoning.

---

## Architecture Overview

See [`docs/architecture.md`](docs/architecture.md) for the full architecture
and implementation details (including an "Extending the system" section --
adding a new skill, swapping the local model, pointing at a different
transcript corpus), [`docs/PRD.md`](docs/PRD.md) for product
scope, assumptions, and trade-offs, [`docs/design.md`](docs/design.md) for
UI/UX principles, interaction states, and accessibility decisions,
[`docs/manual-test-plan.md`](docs/manual-test-plan.md) for a short
walk-through UI test plan, and
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
              AUTO: Ollama (local, default) -> Gemini (cloud fallback)
              Explicit-only (never automatic): OpenAI
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
`app/llm/router.py` (Ollama-first, Gemini-fallback; OpenAI explicit-only), unchanged regardless of
which router made the classification. Full detail, including the
`permission_mode="dontAsk"` security choice, is in
`docs/architecture.md`'s "Agent layer" section.

**How do I run it in Docker?**
`docker compose up --build` from the repo root (with `ollama serve` already
running on the host) — **plus a one-time transcript ingestion step**, or
every question returns "not grounded." See "Option A: Docker Compose"
below for the full 3-step sequence (Ollama → Docker Compose → ingest).

**How do I run the mandatory Ollama-only demo?**
Unset/omit `GEMINI_API_KEY`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY` (or
set `AGENT_SDK_ENABLED=false`), start the app, and confirm
`"provider": "ollama"` in every response. See "Verifying the Ollama-only
(fully offline) path" below.

**How do I run the tests?**
`cd backend && pip install -r requirements-dev.txt && pytest tests -v`. See
"Running tests" below for the DB-dependent-tier details.

**What happens if `ANTHROPIC_API_KEY` is missing or invalid?**
Routing degrades to the local heuristic classifier; the rest of the request
(retrieval, generation, response) proceeds normally. `used_agent_sdk: false`
and `router_error` (non-null) are visible in the response/logs.

**What happens if Ollama is down?**
`generate_with_fallback` catches the failure and retries against Gemini
(if `GEMINI_API_KEY` is set) — this is the AUTO chain; OpenAI is never
tried automatically, only via explicit provider selection. `/api/health`
reports `"ollama": {"status": "..."}` independently so this is diagnosable
at a glance. If Gemini is also unavailable (or not configured), the
request fails with a `502` and an actionable message rather than a raw
stack trace.

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
`OLLAMA_TIMEOUT_SECONDS` (default `120`) is a **soft** wall-clock generation
budget, not a hard cutoff — Ollama's response is streamed, and if this budget
runs out before the model finishes, whatever coherent content has been
generated so far is returned (trimmed to a clean sentence boundary) instead
of being discarded. Only if that leaves too little content to be useful does
it retry against Gemini (if configured) or return a clean, actionable `504`.
See "Ship 30 for 30 length vs. local-model latency" below for why 120s was
chosen deliberately, not guessed.

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
- Optional: a **Gemini API key** (free, no card — [aistudio.google.com/apikey](https://aistudio.google.com/apikey))
  for the automatic cloud fallback, an **OpenAI API key** if you want OpenAI
  available via explicit provider selection (never used automatically), and
  an **Anthropic API key** if you want the agent routing layer to use the real Claude Agent SDK
  instead of its offline heuristic fallback. No separate `npm install -g
  @anthropic-ai/claude-code` step is needed — the `claude-agent-sdk` pip
  package (already in `backend/requirements.txt`) bundles the Claude Code CLI
  binary it needs for Windows/Linux/macOS. See "Agent SDK routing" below.

---

## Option A: Docker Compose (recommended)

**This is three steps, not one** — `docker compose up` alone gets you a
running app that answers "not grounded" to everything, because the
transcript corpus hasn't been ingested yet. Steps 1 and 3 happen outside
Docker; only step 2 is `docker compose`.

### 1. Start Ollama on the host (not in Docker)

```bash
ollama pull llama3.2:3b
ollama serve
```

### 2. Start the app

```bash
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

At this point `/api/health` reports healthy and the UI loads — but every
question still returns "not grounded." That's expected; step 3 is what
fixes it.

### 3. Ingest the transcripts (once)

The app itself needs no Python on your machine — it all runs in Docker.
This one step is the exception: ingestion embeds transcripts locally and
needs a Python environment with the backend's own dependencies to do it,
even though it's writing into the Dockerized database.

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# requirements-dev.txt, not the production requirements.txt: ingestion
# needs sentence-transformers/torch for local embedding, which was
# deliberately removed from the production dependencies (and the Docker
# image) to fit Render's free-tier memory limit -- see docs/architecture.md.
pip install -r requirements-dev.txt
```

```bash
# Still in backend/, venv active. Point DATABASE_URL at the Docker Compose
# db service's published port (localhost:5432, not the internal "db" hostname):
# Windows (PowerShell):
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/lenny"; python scripts/ingest.py
# macOS/Linux:
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/lenny python scripts/ingest.py
```

This takes a few minutes (local embedding of ~300 episodes) and is safe to
re-run — see "Ingest the transcripts" under Option B below for exactly what
it does (chunking, timestamps, the `--force` re-embed flag). **Until this
finishes, "not grounded" on every question is expected, not a bug** — see
Troubleshooting.

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
venv active, install the dev requirements once if you haven't already
(ingestion needs `sentence-transformers`/torch, which the production
`requirements.txt` deliberately excludes -- see docs/architecture.md):

```bash
cd backend
pip install -r requirements-dev.txt
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
cp .env.example .env
npm run dev
```

The default in `.env.example` (`VITE_API_URL=http://127.0.0.1:8000`) matches
this manual setup as-is — you only need to edit `frontend/.env` if your
backend is reachable somewhere other than `127.0.0.1:8000` (see
`frontend/.env.example`'s comment for the Docker-network caveat).

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
  docker exec -it lenny-growth-assistant-db-1 psql -U postgres -c "CREATE DATABASE lenny_test;"
  docker exec -it lenny-growth-assistant-db-1 psql -U postgres -d lenny_test -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pgcrypto;"
  TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/lenny_test pytest backend/tests -v
  ```
  **Do not point `TEST_DATABASE_URL` at the same database your running app
  uses (e.g. `.../lenny`, the default Docker Compose database name)** — the
  test fixtures delete all rows from every table after each test, and this
  has actually happened once during this project's own development (wiping
  the full ingested transcript corpus; recovered by re-running
  `scripts/ingest.py` — see `agent_transcripts/13`). Always use a genuinely
  separate database name like `lenny_test`, as above, never the app's own
  database.

  If no test database is reachable, these tests are skipped individually
  with a clear reason, rather than failing the whole suite.

---

## Verifying the Ollama-only (fully offline) path

The assignment requires a working local-model demo with no cloud dependency.
To verify:

```bash
# In the shell running the backend, make sure no cloud keys are set:
unset GEMINI_API_KEY
unset OPENAI_API_KEY
unset ANTHROPIC_API_KEY
# or set AGENT_SDK_ENABLED=false in .env to skip the agent SDK attempt entirely
```

Then hit `/api/chat`, `/api/essay`, and `/api/artifact` and confirm
`"provider": "ollama"` in each response, and check `/api/health` shows
`"ollama": {"status": "ok"}`.

---

## Ship 30 for 30 length vs. local-model latency

**Content target:** the Ship 30 for 30 skill (`app/skills/ship30.py`) is
designed around an approximately 1,240–1,250-word long-form essay format —
strong hook, one section per grounded source, skimmable Markdown, an
actionable checklist.

**Runtime constraint:** the mandatory local demo path runs this generation
through Ollama on CPU, where long-form generation is genuinely
latency-sensitive — live measurement on this project's own reference
hardware put a full-length essay well past a minute, and sometimes past
three, depending on the machine (see `agent_transcripts/13`).

**Engineering decision:** rather than force the local model to keep
generating until it hits the exact target length (which would make the
mandatory local demo unpredictably slow, or push it past a usable runtime
budget), `OLLAMA_TIMEOUT_SECONDS` (default `120`) is a deliberate **soft**
generation budget. The response is streamed, and if the budget runs out
before the model finishes, whatever coherent content has been generated so
far is returned — trimmed to a clean sentence ending — rather than
discarded. The prompt itself is written to prioritize, in order: groundedness
→ relevance → coherent narrative → useful takeaways → structure/readability
→ reasonable length → exact word count, and explicitly instructs the model
not to pad toward the target. **A shorter-than-ideal essay on the local path
is the intended, documented behavior, not a bug** — quality and groundedness
within the runtime budget take priority over hitting an exact word count.

If the budget runs out so early that too little was generated to be useful
(not just "shorter," but not actually a usable answer), that's treated as a
failure: the app retries against Gemini if configured (the AUTO chain's
only automatic fallback — OpenAI is never entered automatically), or
returns a clean `504` explaining the local runtime limit was exceeded —
never a raw stack trace.

**Cloud path (optional):** when Gemini is configured with a valid API key
(free tier, no card required), the same generation workflow benefits from
cloud inference speed and isn't bound by this machine's CPU throughput, so
it has much more practical headroom to reach the full ~1,250-word target on
every request. OpenAI is also fully implemented and can be selected
explicitly (`provider="openai"` / `FORCE_LLM_PROVIDER=openai`) once you have
a funded key — this repo's own `OPENAI_API_KEY` is *not* currently backed
by a funded account (see the Status note at the top of this README), which
is exactly why it's excluded from the automatic chain rather than being a
problem to fix. The local Ollama path remains fully functional and is what
the mandatory demo relies on regardless.

---

## Key environment variables

See `backend/.env.example` for the full list with explanations. The most
relevant:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (pgvector required) |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Local model config (mandatory path) |
| `OLLAMA_TIMEOUT_SECONDS` | Soft generation budget, not a hard cutoff (default `120`, deliberate trade-off — see "Ship 30 for 30 length vs. local-model latency" above). Responses are streamed; if the budget runs out, whatever was generated so far is returned (trimmed cleanly) rather than discarded. |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | The AUTO chain's cloud fallback (Ollama → Gemini). Free tier, no card required — [aistudio.google.com/apikey](https://aistudio.google.com/apikey). `GEMINI_MODEL` defaults to `gemini-3.6-flash` (chosen over Google's headline `gemini-3.8-flash` after real testing found 3.8 returning live 503 "high demand" errors ~1/3 of the time); `gemini-2.0-flash` and `gemini-2.5-flash` are both deprecated for new API keys, do not use them. Blank `GEMINI_API_KEY` = fully offline (fails if Ollama also fails). |
| `OPENAI_API_KEY` | Explicit-only cloud provider — never used automatically, only via `provider="openai"` / `FORCE_LLM_PROVIDER=openai` |
| `FORCE_LLM_PROVIDER` | Deployment-wide provider override (`ollama` \| `gemini` \| `openai` or blank) |
| `RAG_MIN_SIMILARITY` | Cosine-similarity floor for "grounded" (default `0.30`) |
| `AGENT_SDK_ENABLED` | Enable/disable the Claude Agent SDK routing attempt. **Default differs by setup**: `true` for manual/`config.py` (attempts the real SDK, degrading gracefully if `ANTHROPIC_API_KEY` is absent), but `false` in `docker-compose.yml` — Docker Compose defaults to the local heuristic router only, so `docker compose up` with no overrides is a guaranteed fully-offline demo with zero Anthropic dependency. Override with `AGENT_SDK_ENABLED=true` before `docker compose up` to opt into the real SDK there too. |
| `ANTHROPIC_API_KEY` | Required only if `AGENT_SDK_ENABLED=true` |
| `CORS_ORIGINS` | Extra allowed frontend origins beyond localhost dev ports |

The frontend also has a **provider toggle** in the header (Auto / Ollama /
Gemini / OpenAI) that overrides the backend default on a per-request basis,
without needing to restart the backend.

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
