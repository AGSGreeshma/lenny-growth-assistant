# Product Requirements Document — The Lenny Growth Assistant

## 1. User & Problem

**Primary user:** A product manager or growth lead who follows Lenny's Podcast for
tactical advice but doesn't have time to listen to 300+ hours of interviews to find
the specific guidance relevant to their current problem.

**Job to be done:** "When I'm facing a specific growth/product question (e.g. "how do
I improve activation for a B2B SaaS product"), help me find what guests who've solved
this before actually said — with enough detail and attribution that I can trust and
act on it, without me having to remember which episode or guest covered it."

**Pain removed:** Podcast knowledge is currently locked inside unsearchable audio/long
transcripts. The user either skims transcripts manually or gives up and asks a generic
LLM, which has no guarantee of grounding in real operator experience. This assistant
makes 300+ episodes queryable like a colleague who's listened to all of them.

## 2. Success Metrics

- **Retrieval relevance:** ≥90% of test queries return at least one chunk with
  cosine similarity ≥0.5 to the query, verified against a hand-built set of ~15
  representative growth/PM questions.
- **Grounding integrity:** 0% of answers cite an episode/guest that isn't actually
  present in the retrieved context (verified by spot-checking answer citations
  against the `sources` array returned by `/ask`).
- **Latency:** local (Ollama) answers return in <60s on commodity hardware; cloud
  fallback answers return in <10s. (Operational target, not a hard SLA for this
  demo — see Risks below.)

## 3. Assumptions

The original take-home brief didn't fully specify these, so the following were assumed:

- The [Lenny's Podcast transcript archive](https://github.com/) used for ingestion
  (303 episodes, pre-chunked by guest, with a topic index) is an acceptable
  substitute for a live scraping/refresh pipeline — a one-time ingestion is
  sufficient for this demo; a production system would need a scheduled refresh job.
- "Session" means a single browser tab's conversation thread, not a durable
  multi-device user account — no login/auth was in scope for this assessment.
- "Local model that works comfortably on your machine" was interpreted as a
  small Ollama model (`llama3.2:3b`, chosen over the initially-tried `llama3.1`
  8B for acceptable response latency on CPU-only hardware), with a documented
  fallback to a cloud model (OpenAI) when local inference is too slow or Ollama
  is unavailable — see Risks.
- Grounding threshold: rather than hard-rejecting low-similarity retrievals, the
  system passes the top-k chunks and instructs the model to explicitly say when
  the material is insufficient. This was chosen over a similarity cutoff because a
  hard threshold risked over-rejecting valid but loosely-worded matches.

## 4. Scope

**In scope:**
- RAG-grounded Q&A over the full transcript archive, with per-answer source citations
- Multi-turn sessions with persisted history (Postgres)
- Ship 30 for 30 essay generation from a grounded answer
- Markdown/HTML artifact rendering in a sandboxed in-app viewer
- Dual LLM configuration: Ollama (local, default/required for demo) with automatic
  fallback to a cloud provider (Anthropic Claude) on timeout or failure
- Structured logging, health endpoint, graceful degradation on DB/model failures

**Explicitly out of scope (and why):**
- User authentication / multi-user accounts — not required by the brief; sessions
  are anonymous and scoped to a browser session
- Live/scheduled transcript refresh — one-time ingestion is sufficient to
  demonstrate the ingestion → retrieval → grounding pipeline end-to-end
- Production-grade horizontal scaling / load balancing — this is a local,
  single-instance demo per the assignment's deployment requirements

## 5. Key Flows

1. **Ask a question** → user types a question → backend retrieves top-k transcript
   chunks → LLM generates a grounded, cited answer → frontend renders answer +
   source cards.
2. **Follow-up question** → same session_id is reused → prior turns are included as
   context → retrieval + generation repeat.
3. **Generate an essay** → user requests a Ship 30 for 30-style writeup of a prior
   grounded answer → dedicated skill reformats it into a ~1,250-word essay →
   rendered as a Markdown artifact in the side panel.
4. **Model failure** → if Ollama is unreachable or times out, the system logs a
   warning and automatically retries the same request against the cloud provider,
   so the user experience degrades gracefully rather than failing outright.

## 6. Acceptance Criteria

- A new session can be started and maintains independent conversation context from
  other sessions.
- Every grounded answer includes at least one source citation traceable to a real
  transcript chunk.
- When no relevant transcript material exists, the assistant says so rather than
  fabricating an answer.
- The Ship 30 for 30 skill produces a distinctly-formatted essay (headers, bullets,
  bold anchors) grounded in the same retrieved material as the underlying answer.
- Generated HTML artifacts render in a sandboxed iframe that cannot access
  parent-page cookies or storage.
- The system starts from a documented, repeatable setup process and reports its
  own health (API, DB, model availability) via `/api/health`.

## 7. Risks & Trade-offs

- **Local model latency/reliability:** an 8B model on CPU-only hardware can take
  30-60+ seconds per response, and Ollama can drop idle-loaded models from memory
  between requests, causing timeouts. Mitigated with `keep_alive` tuning and an
  automatic cloud fallback — but this remains the single biggest reliability risk
  in the local-only demo path.
- **Hallucination:** grounding is prompt-enforced, not structurally guaranteed — a
  model can still ignore instructions and answer from parametric knowledge. Mitigated
  by requiring citations and spot-checking them against retrieved sources, but not
  eliminated.
- **Cost/latency trade-off of the cloud fallback:** falling back to a paid API on
  every local hiccup could get expensive at scale; for this demo it's acceptable
  given low query volume.
- **Data leakage:** transcript content and any user questions sent to the cloud
  fallback leave the local machine. Documented in README; acceptable for this demo
  since transcripts are already public podcast content.
- **Unsafe artifact rendering:** LLM-generated HTML is treated as untrusted and
  rendered in a sandboxed iframe (`sandbox="allow-scripts"`, no `allow-same-origin`)
  plus DOMPurify sanitization, to prevent XSS/cookie theft from the parent app.

## 1. User & Problem

**Primary user:** A product manager or growth lead who follows Lenny's Podcast for
tactical advice but doesn't have time to listen to 300+ hours of interviews to find
the specific guidance relevant to their current problem.

**Job to be done:** "When I'm facing a specific growth/product question (e.g. "how do
I improve activation for a B2B SaaS product"), help me find what guests who've solved
this before actually said — with enough detail and attribution that I can trust and
act on it, without me having to remember which episode or guest covered it."

**Pain removed:** Podcast knowledge is currently locked inside unsearchable audio/long
transcripts. The user either skims transcripts manually or gives up and asks a generic
LLM, which has no guarantee of grounding in real operator experience. This assistant
makes 300+ episodes queryable like a colleague who's listened to all of them.

## 2. Success Metrics

- **Retrieval relevance:** ≥90% of test queries return at least one chunk with
  cosine similarity ≥0.5 to the query, verified against a hand-built set of ~15
  representative growth/PM questions.
- **Grounding integrity:** 0% of answers cite an episode/guest that isn't actually
  present in the retrieved context (verified by spot-checking answer citations
  against the `sources` array returned by `/ask`).
- **Latency:** local (Ollama) answers return in <60s on commodity hardware; cloud
  fallback answers return in <10s. (Operational target, not a hard SLA for this
  demo — see Risks below.)

## 3. Assumptions

The original take-home brief didn't fully specify these, so the following were assumed:

- The [Lenny's Podcast transcript archive](https://github.com/) used for ingestion
  (303 episodes, pre-chunked by guest, with a topic index) is an acceptable
  substitute for a live scraping/refresh pipeline — a one-time ingestion is
  sufficient for this demo; a production system would need a scheduled refresh job.
- "Session" means a single browser tab's conversation thread, not a durable
  multi-device user account — no login/auth was in scope for this assessment.
- "Local model that works comfortably on your machine" was interpreted as an 8B
  parameter model (`llama3.1`) run via Ollama on a CPU-only Windows laptop, with a
  documented fallback to a cloud model when local inference is too slow or Ollama
  is unavailable — see Risks.
- Grounding threshold: rather than hard-rejecting low-similarity retrievals, the
  system passes the top-k chunks and instructs the model to explicitly say when
  the material is insufficient. This was chosen over a similarity cutoff because a
  hard threshold risked over-rejecting valid but loosely-worded matches.

## 4. Scope

**In scope:**
- RAG-grounded Q&A over the full transcript archive, with per-answer source citations
- Multi-turn sessions with persisted history (Postgres)
- Ship 30 for 30 essay generation from a grounded answer
- Markdown/HTML artifact rendering in a sandboxed in-app viewer
- Dual LLM configuration: Ollama (local, default/required for demo) with automatic
  fallback to a cloud provider (Anthropic Claude) on timeout or failure
- Structured logging, health endpoint, graceful degradation on DB/model failures

**Explicitly out of scope (and why):**
- User authentication / multi-user accounts — not required by the brief; sessions
  are anonymous and scoped to a browser session
- Live/scheduled transcript refresh — one-time ingestion is sufficient to
  demonstrate the ingestion → retrieval → grounding pipeline end-to-end
- Production-grade horizontal scaling / load balancing — this is a local,
  single-instance demo per the assignment's deployment requirements

## 5. Key Flows

1. **Ask a question** → user types a question → backend retrieves top-k transcript
   chunks → LLM generates a grounded, cited answer → frontend renders answer +
   source cards.
2. **Follow-up question** → same session_id is reused → prior turns are included as
   context → retrieval + generation repeat.
3. **Generate an essay** → user requests a Ship 30 for 30-style writeup of a prior
   grounded answer → dedicated skill reformats it into a ~1,250-word essay →
   rendered as a Markdown artifact in the side panel.
4. **Model failure** → if Ollama is unreachable or times out, the system logs a
   warning and automatically retries the same request against the cloud provider,
   so the user experience degrades gracefully rather than failing outright.

## 6. Acceptance Criteria

- A new session can be started and maintains independent conversation context from
  other sessions.
- Every grounded answer includes at least one source citation traceable to a real
  transcript chunk.
- When no relevant transcript material exists, the assistant says so rather than
  fabricating an answer.
- The Ship 30 for 30 skill produces a distinctly-formatted essay (headers, bullets,
  bold anchors) grounded in the same retrieved material as the underlying answer.
- Generated HTML artifacts render in a sandboxed iframe that cannot access
  parent-page cookies or storage.
- The system starts from a documented, repeatable setup process and reports its
  own health (API, DB, model availability) via `/api/health`.

## 7. Risks & Trade-offs

- **Local model latency/reliability:** an 8B model on CPU-only hardware can take
  30-60+ seconds per response, and Ollama can drop idle-loaded models from memory
  between requests, causing timeouts. Mitigated with `keep_alive` tuning and an
  automatic cloud fallback — but this remains the single biggest reliability risk
  in the local-only demo path.
- **Hallucination:** grounding is prompt-enforced, not structurally guaranteed — a
  model can still ignore instructions and answer from parametric knowledge. Mitigated
  by requiring citations and spot-checking them against retrieved sources, but not
  eliminated.
- **Cost/latency trade-off of the cloud fallback:** falling back to a paid API on
  every local hiccup could get expensive at scale; for this demo it's acceptable
  given low query volume.
- **Data leakage:** transcript content and any user questions sent to the cloud
  fallback leave the local machine. Documented in README; acceptable for this demo
  since transcripts are already public podcast content.
- **Unsafe artifact rendering:** LLM-generated HTML is treated as untrusted and
  rendered in a sandboxed iframe (`sandbox="allow-scripts"`, no `allow-same-origin`)
  plus DOMPurify sanitization, to prevent XSS/cookie theft from the parent app.