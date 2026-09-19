# Architecture — The Lenny Growth Assistant

## Implementation status (read this first)

**Built and working, end-to-end:** transcript ingestion (parses real guest/title/
YouTube-URL metadata from frontmatter), chunking, embedding, pgvector storage and
retrieval with a hard relevance floor, grounded Q&A, multi-turn session persistence
with follow-up context, the Ship 30 for 30 essay skill, the HTML/CSS artifact skill,
the sandboxed artifact viewer, automatic Ollama→OpenAI fallback with a per-request
provider override, a pytest suite, and Docker Compose packaging.

## Component overview

```
┌─────────────┐      HTTP/JSON       ┌──────────────────┐
│  Frontend    │ ───────────────────▶│  FastAPI backend  │
│  (React/Vite)│◀─────────────────── │                    │
└─────────────┘                      └─────────┬─────────┘
                                                 │
                ┌───────────────┬────────────────┼────────────────┬──────────────────┐
                ▼               ▼                ▼                ▼                  ▼
        ┌───────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
        │  PostgreSQL    │ │  Embedding   │ │  LLM router   │ │  Agent layer  │ │  Skills       │
        │  + pgvector    │ │  model       │ │  (app/llm/    │ │  (Claude      │ │  (Ship 30,    │
        │                │ │ (sentence-   │ │  router.py)   │ │  Agent SDK,   │ │  HTML         │
        │                │ │ transformers)│ │  Ollama first,│ │  routing      │ │  artifact)    │
        │                │ │              │ │  OpenAI       │ │  only)        │ │               │
        │                │ │              │ │  fallback     │ │               │ │               │
        └───────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

## Database schema

```sql
CREATE TABLE transcript_chunks (
    id BIGSERIAL PRIMARY KEY,
    episode_title TEXT NOT NULL,
    episode_url   TEXT,
    chunk_text    TEXT NOT NULL,
    speaker       TEXT,
    timestamp     TEXT,
    embedding     VECTOR(384) NOT NULL
);
CREATE INDEX ON transcript_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    client_label TEXT,  -- optional anonymous client label, not a user identity
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources JSONB,
    artifact_type TEXT,  -- 'markdown' or 'html', NULL for normal replies
    created_at TIMESTAMPTZ DEFAULT now()
);
```

No separate `artifacts` table: an essay or HTML artifact is stored as a
`messages` row with `artifact_type` set, keeping session history and
artifacts in one timeline rather than a parallel structure. This was a
deliberate scope simplification given the timeline for this assessment.

`app/database.py`'s `ensure_schema()` creates the `vector`/`pgcrypto`
extensions, runs `Base.metadata.create_all()`, applies additive
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` fixes, and creates the HNSW
vector index (`CREATE INDEX IF NOT EXISTS ... USING hnsw`) at every app
startup -- the index isn't expressible as a plain SQLAlchemy column
attribute, so `create_all()` alone wouldn't create it; without this explicit
statement a fresh database would silently retrieve via sequential scan
instead of the index. All of this together means a fresh database (e.g. the
Docker Compose `db` service on its first run) needs no manual migration
step. `backend/scripts/setup_db.sql` and
`backend/create_tables.py` remain as manual alternatives.

## API endpoints

- `GET /` — liveness check
- `GET /api/health` — reports DB, Ollama, and embedding-model status
  individually, plus an overall `healthy`/`degraded`/`unavailable` rollup
- `POST /api/sessions` — create a new session (optional `client_label`),
  returns `session_id`
- `GET /api/sessions/{id}` — fetch full message history for a session
- `POST /api/chat` — `{session_id, message, provider?}` → the agent layer
  classifies intent (chat / essay / html_artifact) and routes accordingly;
  returns a grounded, cited answer and, for essay/html_artifact intents, an
  `artifact` object; persists both turns; includes the last few exchanges as
  context for follow-up questions
- `POST /api/essay` — `{session_id, topic, provider?}` → Ship 30 for 30
  Markdown essay, grounded in fresh retrieval on the topic; persisted as an
  artifact message
- `POST /api/artifact` — `{session_id, topic, provider?}` → sanitized,
  self-contained HTML/CSS artifact, grounded in fresh retrieval on the topic;
  persisted as an artifact message

`/api/essay` and `/api/artifact` exist as dedicated endpoints for the
frontend's explicit buttons; `/api/chat` additionally infers the same intents
from a natural-language request (e.g. "give me this as an HTML page") via the
agent layer, so both paths produce the same artifact shape.

## Ingestion → retrieval flow

1. `backend/scripts/ingest.py` reads each transcript's YAML frontmatter
   (`guest`, `title`, `youtube_url`) plus its body. For the corpus's
   dominant format (301/303 transcripts: `Speaker (HH:MM:SS):` turn
   headers), it parses the body into individual speaker turns and groups
   whole turns into ~3000-character chunks with turn-based overlap (`
   parse_turns()`/`chunk_turns()`) — chunks never split mid-turn or
   mid-sentence, and each chunk records the real timestamp and speaker of
   its first turn. The remaining 2 transcripts (which use different, one-off
   formats) fall back to the original raw ~3000-character/500-character
   sliding-window split with no timestamp, exactly as every transcript used
   to be chunked (`build_chunks()`). Every chunk is embedded with
   `all-MiniLM-L6-v2` (384-dim, local, no API cost) and inserted into
   `transcript_chunks` via SQLAlchemy. Re-running ingestion skips episodes
   that already have chunks stored (by episode title) unless `--force` is
   passed, so adding new transcript files and re-running only ingests what's
   new.
2. On each `/api/chat`, `/api/essay`, or `/api/artifact` request,
   `TranscriptRetriever` embeds the query the same way and runs a
   cosine-similarity search over the pgvector HNSW index, then drops any
   chunk scoring below `RAG_MIN_SIMILARITY` (default 0.30) before returning
   the rest. An out-of-domain query that still yields *some* nearest
   neighbours (pgvector's `ORDER BY ... LIMIT` always returns something) is
   therefore not treated as evidence just because rows came back.
3. If no chunks clear the floor, the caller returns a fixed
   `NOT_GROUNDED_MESSAGE` with **no LLM call at all** — grounding is a
   structural property of the pipeline, not something the model is merely
   asked to self-report.
4. Otherwise, chunks are formatted into a numbered `SOURCE` block and passed
   to the LLM router with a system prompt requiring grounding and citation.
5. The frontend renders the answer plus a `SourceCard` per chunk, including a
   clickable YouTube link and similarity score.

## Model routing / dual-provider design

`app/llm/ollama_client.py` and `app/llm/openai_client.py` share a consistent
`generate(messages, system_prompt)` interface. `app/llm/router.py` is the
single place fallback logic lives: it calls Ollama first (satisfying "local
model required for the demo"), and on any failure (timeout, connection error),
logs a warning and retries against OpenAI — used identically by every
generation path (`rag/generator.py`, `skills/ship30.py`,
`skills/html_artifact.py`), so the fallback behavior is consistent everywhere
an answer is generated.

Two ways to override the default Ollama-first behavior:
- `FORCE_LLM_PROVIDER=openai` (env var, deployment-wide) bypasses Ollama
  entirely; unset it when demonstrating the required local model path.
- A per-request `provider` field (`"ollama" | "openai" | null`) on
  `ChatRequest`/`EssayRequest`/`ArtifactRequest`, surfaced in the frontend as
  a provider toggle in the header. This takes precedence over
  `FORCE_LLM_PROVIDER` for that request; requesting `"ollama"` explicitly
  fails loudly on error rather than silently falling back to OpenAI, since
  the caller asked for a specific provider.

## Agent layer (Claude Agent SDK)

`app/agent/orchestrator.py` uses the Claude Agent SDK for exactly one job:
classifying a chat message's intent (`chat` / `essay` / `html_artifact`),
optionally calling a `retrieve_transcripts` MCP tool (`app/agent/tools.py`)
to check the knowledge base first. It never writes the final answer text —
every generation path still flows through `generate_with_fallback`
(Ollama-first, OpenAI-fallback), completely unchanged. This is deliberate:
the Agent SDK talks to the Anthropic API only, so if it wrote answers
directly, every successful request would silently become cloud-generated,
making the "local model mandatory for the demo" requirement untestable. See
the module's docstring for the full reasoning.

**How the SDK reaches Anthropic, and what it needs installed.** The
`claude-agent-sdk` pip package (pinned to `0.2.156` in `requirements.txt`)
spawns a local Claude Code CLI process and talks to it over stdio; that CLI
process is what actually calls the Anthropic API. On Windows, Linux, and
macOS, that CLI binary ships *bundled inside the pip wheel itself*
(`claude_agent_sdk/_bundled/`) — `pip install -r requirements.txt` is
sufficient. No separate `npm install -g @anthropic-ai/claude-code` step and
no `claude` CLI on `PATH` are required. Authentication is via
`ANTHROPIC_API_KEY` (the documented, reproducible path — see
`.env.example`); the bundled CLI can also pick up an interactive
`claude login` session from a developer's own machine, but that session
lives outside the repo and isn't something an evaluator needs to set up.
0.2.156 was chosen deliberately, not left unpinned: the very next release
(0.2.157) dropped the Windows wheel from PyPI entirely, so an unpinned
install on Windows would silently fall back to a source build with no
bundled CLI binary at all.

**Permission mode: `dontAsk`, not `bypassPermissions`.** The router only
ever needs one narrow, read-only tool
(`mcp__lenny__retrieve_transcripts`, pre-approved via `allowed_tools`); it
never needs file edits or shell access. `permission_mode="dontAsk"` lets
that one pre-approved tool run without an interactive prompt (there's no
terminal to prompt in a server process) while denying everything else by
default — least-privilege, and it never sends the CLI's
`--dangerously-skip-permissions` flag. `bypassPermissions` was tried first
and rejected for two reasons: it auto-approves *every* tool call, not just
the one this router needs, and the bundled CLI additionally refuses to
honor it when the process runs as root — which a default Docker container
does, since `backend/Dockerfile` sets no `USER` directive. Switching the
container to a non-root user was considered and rejected in favor of this
one-line, more-restrictive permission change: it fixes the root case too,
needs no Dockerfile/compose changes, and is strictly narrower regardless of
which user the process runs as. Verified live: inside the Docker container
(running as root), calling the real `_classify_via_agent_sdk()` with a
placeholder `ANTHROPIC_API_KEY` reaches Anthropic's authentication stage
and receives a clean `401 API key is invalid` — not a permissions/root
refusal.

If the SDK is unavailable for any reason (no key configured, no login
session, network unreachable, CLI process error), routing degrades to a
deterministic keyword classifier (`_classify_via_heuristics`) so the app
keeps working end-to-end with zero cloud dependency — which is also what the
mandatory offline/Ollama demo needs. `AGENT_SDK_ENABLED=false` skips the SDK
attempt entirely. Every routing decision records `used_agent_sdk: bool` so
this is visible in API responses and logs, not silently papered over.

## Security: artifact rendering

Generated content is treated as untrusted by the viewer, regardless of type:

- **Markdown** (produced by the Ship 30 skill) renders through
  `react-markdown` + `remark-gfm` (`AnswerContent.jsx`). react-markdown does
  not use `dangerouslySetInnerHTML` by default and raw HTML embedded in
  Markdown is not rendered as HTML, so there is no HTML injection surface on
  this path.
- **HTML** (produced by the HTML/CSS artifact skill, `skills/html_artifact.py`)
  goes through two independent layers before it reaches the user:
  1. **Server-side sanitization** (`sanitize_html()`): a dependency-free,
     regex-based pass that strips `<script>` tags, inline event handler
     attributes (`onclick=` etc.), and `javascript:` URLs before the HTML is
     ever stored or returned by the API. This is defense-in-depth, not the
     primary boundary — a sufficiently obscure payload could theoretically
     slip past a regex-based pass.
  2. **Sandboxed rendering**: the frontend renders the (already-sanitized)
     HTML inside `<iframe srcDoc={...} sandbox="allow-scripts">` with
     `allow-same-origin` deliberately omitted. This is the primary boundary:
     even HTML that slipped past the sanitizer runs in an origin with no
     access to the parent page's cookies or `localStorage`, and cannot
     navigate or script the parent frame.

  No DOMPurify or other client-side HTML-sanitization library is currently
  used; the two layers above are the full threat model for this feature. A
  client-side DOMPurify pass would be a reasonable additional layer if this
  went to production, but was judged redundant with the sandboxed iframe for
  this assessment's scope.

## Deployment topology

**Docker Compose** (`docker-compose.yml`, `backend/Dockerfile`,
`frontend/Dockerfile`): a `pgvector/pgvector:pg16` Postgres service, the
FastAPI backend, and an nginx-served static build of the frontend. Ollama is
documented as host-run, not containerized — the backend reaches it at
`http://host.docker.internal:11434`, so `ollama serve` (with the model
pulled) must already be running on the host before `docker compose up`.

**Manual (no Docker):** `uvicorn` (backend) + Vite dev server (frontend) +
Postgres/pgvector (Supabase-hosted, or any reachable instance) + a local
`ollama serve` process. See the README for exact commands.

**Known hardware caveat: GPU/CUDA failures on Ollama's side are a host
issue, not a code issue.** On one development machine, Ollama's GPU worker
process crashed on every request (`exit status 0xc0000409` — a Windows
stack-buffer-overrun — during `CUDA error: shared object initialization
failed`), which is a driver/CUDA-runtime incompatibility, not anything in
this codebase. Symptoms looked like a hang from the app's side (every
`/api/chat`/`/api/essay`/`/api/artifact` request would time out after
~3 minutes with no response) because Ollama's own supervisor kept silently
retrying a GPU worker that would never come up, occasionally leaving
multiple zombie `ollama.exe` processes stacked up. The fix was host-level,
not code-level: restart Ollama with `CUDA_VISIBLE_DEVICES=-1` (or
`OLLAMA_LLM_LIBRARY=cpu`) to force CPU-only inference, bypassing the broken
CUDA path. CPU-only inference is slower and pushed real generation times for
the longer skills above the previous 180s timeout (see
`OLLAMA_TIMEOUT_SECONDS` below) but is otherwise fully functional and was
verified end-to-end through the real running app. If Ollama appears
unresponsive, check `ollama ps` for zombie processes and the Ollama app's
own `server.log` for `CUDA error` / `GPU discovery watchdog timed out`
before assuming it's an application bug.

## Observability & resilience

- Structured logging (`lenny-assistant` logger) captures retrieval and
  generation failures with full tracebacks.
- `/api/health` independently reports DB, Ollama, and embedding-model status,
  plus an overall rollup: `healthy` (all three ok), `degraded` (e.g. Ollama
  down but `OPENAI_API_KEY` configured, so the app still answers), or
  `unavailable` (DB or embeddings down, or no LLM path reachable at all).
- `/api/chat`, `/api/essay`, and `/api/artifact` wrap retrieval and
  generation in separate try/except blocks, returning a `502` with an
  actionable message ("Check DB connection" vs. "Check Ollama/API is
  running") rather than a raw stack trace.
- Empty questions/messages/topics are rejected with a `400` before any DB or
  model call.
- The Ollama→OpenAI fallback means a stopped or slow local model degrades to a
  working cloud answer rather than failing the request outright.
