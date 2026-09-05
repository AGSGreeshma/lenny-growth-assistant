# Architecture — The Lenny Growth Assistant

## Implementation status (read this first)

**Built and working, end-to-end:** transcript ingestion (parses real guest/title/
YouTube-URL metadata from frontmatter), chunking, embedding, pgvector storage and
retrieval, grounded Q&A, multi-turn session persistence with follow-up context,
the Ship 30 for 30 essay skill, the sandboxed artifact viewer, and automatic
Ollama→OpenAI fallback.

**Not yet built:** Docker Compose packaging (manual multi-terminal setup is
documented in the README instead), a converted pytest suite (current tests are
loose scripts), and a visible model-provider indicator in the UI (the fallback
works correctly but happens silently).

## Component overview

```
┌─────────────┐      HTTP/JSON       ┌──────────────────┐
│  Frontend    │ ───────────────────▶│  FastAPI backend  │
│  (React/Vite)│◀─────────────────── │                    │
└─────────────┘                      └─────────┬─────────┘
                                                 │
                        ┌────────────────────────┼────────────────────────┐
                        ▼                        ▼                        ▼
                ┌───────────────┐      ┌──────────────────┐     ┌──────────────────┐
                │  PostgreSQL   │      │  Embedding model  │     │  LLM router        │
                │  + pgvector   │      │ (sentence-        │     │  (app/llm/router)   │
                │  (Supabase)   │      │  transformers)    │     │  Ollama first,       │
                └───────────────┘      └──────────────────┘     │  OpenAI fallback     │
                                                                  └──────────────────┘
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
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources JSONB,
    artifact_type TEXT,  -- 'markdown' for Ship 30 essays, NULL for normal replies
    created_at TIMESTAMPTZ DEFAULT now()
);
```

No separate `artifacts` table: a Ship 30 essay is stored as a `messages` row with
`artifact_type='markdown'`, keeping session history and artifacts in one
timeline rather than a parallel structure. This was a deliberate scope
simplification given the timeline for this assessment.

## API endpoints

- `GET /` — liveness check
- `GET /api/health` — reports API + DB connectivity
- `POST /ask` — legacy stateless single-turn endpoint (kept for backward
  compatibility; new work should use `/api/chat`)
- `POST /api/sessions` — create a new session, returns `session_id`
- `GET /api/sessions/{id}` — fetch full message history for a session
- `POST /api/chat` — `{session_id, message}` → grounded, cited answer;
  persists both turns; includes the last 3 exchanges as context for
  follow-up questions
- `POST /api/essay` — `{session_id, topic}` → Ship 30 for 30 Markdown essay,
  grounded in fresh retrieval on the topic; persisted as an artifact message

## Ingestion → retrieval flow

1. `backend/scripts/ingest.py` reads each transcript's YAML frontmatter
   (`guest`, `title`, `youtube_url`) plus its body, splits the body into
   ~3000-character chunks with 500-character overlap, embeds each chunk with
   `all-MiniLM-L6-v2` (384-dim, local, no API cost), and inserts into
   `transcript_chunks` via SQLAlchemy.
2. On each `/api/chat` or `/ask` request, `TranscriptRetriever` embeds the
   query the same way and runs a cosine-similarity search over the pgvector
   HNSW index, returning the top-k chunks with episode, guest, URL, and score.
3. Chunks are formatted into a numbered `SOURCE` block and passed to the LLM
   router with a system prompt requiring grounding and citation.
4. The frontend renders the answer plus a `SourceCard` per chunk, including a
   clickable YouTube link and similarity score.

## Model routing / dual-provider design

`app/llm/ollama_client.py` and `app/llm/openai_client.py` share a consistent
`generate(messages, system_prompt)` interface. `app/llm/router.py` is the
single place fallback logic lives: it calls Ollama first (satisfying "local
model required for the demo"), and on any failure (timeout, connection error),
logs a warning and retries against OpenAI -- used identically by both the
grounded-answer path (`rag/generator.py`) and the Ship 30 skill
(`skills/ship30.py`), so the fallback behavior is consistent everywhere an
answer is generated.

A `FORCE_LLM_PROVIDER=openai` environment variable bypasses Ollama entirely for
fast local iteration; it should be unset when demonstrating the required local
model path.

## Security: artifact rendering

Generated content is treated as untrusted by the viewer, regardless of type:
- **Markdown** (currently the only type actually produced, by the Ship 30
  skill) renders through the same plain-text-to-React renderer used for chat
  answers (`AnswerContent.jsx`) -- it never touches `dangerouslySetInnerHTML`,
  so there is no HTML injection surface on this path at all.
- **HTML** (supported by the viewer's code path for future use, not currently
  exercised by any skill) renders inside `<iframe srcDoc={...}
  sandbox="allow-scripts">` with `allow-same-origin` deliberately omitted --
  this blocks the iframe from reading the parent page's cookies or
  localStorage even if the generated HTML contained a malicious script.

## Deployment topology

Local dev: `uvicorn` (backend) + Vite dev server (frontend) + Supabase-hosted
Postgres/pgvector + a local `ollama serve` process. Docker Compose packaging
is not yet implemented; the manual multi-terminal setup is documented step by
step in the README as the current run path.

## Observability & resilience

- Structured logging (`lenny-assistant` logger) captures retrieval and
  generation failures with full tracebacks in both `/ask` and `/api/chat`.
- `/api/health` independently reports DB connectivity.
- Both `/ask` and `/api/chat` wrap retrieval and generation in separate
  try/except blocks, returning a `502` with an actionable message ("Check DB
  connection" vs. "Check Ollama/API is running") rather than a raw stack trace.
- Empty questions/messages/topics are rejected with a `400` before any DB or
  model call.
- The Ollama→OpenAI fallback means a stopped or slow local model degrades to a
  working cloud answer rather than failing the request outright.