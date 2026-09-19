# Product Requirements Document — The Lenny Growth Assistant

# 1. Product Overview

The Lenny Growth Assistant is a RAG-powered internal tool that turns Lenny's
Podcast transcripts into a conversational, cited assistant for product/growth
questions, with two writing skills (a Ship 30 for 30 essay and an HTML/CSS
one-pager) built on top of the same grounded material.

## 1.1 Key Flows

1. **Ask a question** → user types a question → the agent layer classifies intent →
   backend retrieves top-k transcript chunks → LLM generates a grounded, cited answer
   → frontend renders answer + source cards.
2. **Follow-up question** → same session_id is reused → prior turns are included as
   context → retrieval + generation repeat.
3. **Generate an essay** → user requests a Ship 30 for 30-style writeup (either via
   the dedicated button or by asking for it in chat) → dedicated skill reformats
   grounded material into an essay targeting ~1,240-1,250 words as an ideal, not a
   hard requirement (see 2.5's latency trade-off) → rendered as a Markdown artifact
   in the side panel.
4. **Generate an HTML artifact** → user asks for a one-pager/HTML page → dedicated
   skill produces a self-contained, sanitized HTML document → rendered in a
   sandboxed iframe in the side panel.
5. **Model failure** → if Ollama is unreachable or times out, the system logs a
   warning and automatically retries the same request against the cloud provider
   (when configured), so the user experience degrades gracefully rather than
   failing outright.

## 1.2 Acceptance Criteria

- A new session can be started and maintains independent conversation context from
  other sessions.
- Every grounded answer includes at least one source citation traceable to a real
  transcript chunk.
- When no relevant transcript material exists, the assistant says so structurally
  (no LLM call is made) rather than fabricating an answer.
- The Ship 30 for 30 skill produces a distinctly-formatted essay (headers, bullets,
  bold anchors) grounded in the same retrieved material as the underlying answer,
  targeting ~1,240-1,250 words as an ideal length -- on the local Ollama path this
  is a soft target the model is not forced to pad toward (see 2.5's latency
  trade-off); a shorter, complete, grounded essay is acceptable when the runtime
  budget is spent.
- Generated HTML artifacts are sanitized server-side and render in a sandboxed
  iframe that cannot access parent-page cookies or storage.
- The system starts from a documented, repeatable setup process (manual or Docker
  Compose) and reports its own health (API, DB, Ollama, embedding model) via
  `/api/health`.

---

# 2. Forward Deployment Brief

## 2.1 User and Problem

**Primary user:** the product/growth team described in the assignment — the
internal audience this tool is built for, not a hypothetical external
customer.

**Job to be done:** when someone on that team is facing a specific
product/growth question (e.g. "how do I improve activation for a B2B SaaS
product"), they want to find what guests who've actually solved this before
said — with enough detail and attribution to trust and act on it — without
first needing to know which of 300+ episodes to search, or how to operate an
LLM, a vector database, or a prompt to get there.

**Current pain/friction:** the assignment frames this directly — the team
wants grounded answers, reusable written content, and rendered artifacts
*without needing to understand prompts, models, or infrastructure*. Absent
this tool, that knowledge is only reachable by manually searching or
listening through the transcript archive, or by asking a general-purpose LLM
that has no guarantee of grounding in what a guest actually said versus what
sounds plausible.

**What the assistant removes:** the need to (a) know which episode covers a
topic, (b) manually search/skim transcripts, and (c) manually reshape a
grounded answer into a shareable written format (an essay or a one-pager)
when the team wants to reuse it, rather than just read it once in a chat
window.

**Why grounding in the transcript archive specifically matters:** the value
this tool offers over a generic chatbot is that its answers are traceable to
real operator experience the team already trusts (Lenny's guests), not
generic internet advice. If an answer can't be traced to a specific episode
and guest, it isn't more useful than asking any other LLM — so grounding
(and showing the grounding, via source citations) is the core of the product,
not a nice-to-have on top of it.

## 2.2 Success Metrics

Targets below are **proposed targets for this engagement**, not observed
production baselines — there is no prior deployment to draw a baseline from.
Where a number *was* actually measured during this project (not just
proposed), it's labeled "Observed."

| # | Metric | Definition | Target | How measured |
|---|---|---|---|---|
| 1 (product/user) | **Grounded Response Rate on In-Domain Questions** | Proportion of realistic product/growth questions (drawn from topics the corpus actually covers) that receive a grounded, cited answer rather than the "not grounded" fallback. | Proposed target: ≥90% against a hand-built set of ~15 representative questions. | Run the question set against `/api/chat`, check `grounded: true` in each response. |
| 2 (grounding/reliability) | **Citation Traceability Rate** | Proportion of citations in a grounded response that correspond to a transcript chunk actually returned by the retriever for that query (i.e., no fabricated sources). | Target: 100%, by construction. | The `sources` array is built directly in code from the retriever's returned chunks (`app/api/chat.py`'s `to_source()`) — it is never parsed out of the LLM's free-text output, so a citation cannot exist without a matching retrieved chunk. This is a structural/code-level guarantee, not something sampled after the fact. |
| 3 (operational) | **Local (Ollama) Generation Latency** | Wall-clock time from request received to response returned, on the local/CPU-only path. | Proposed target: a useful response within a configurable soft budget (`OLLAMA_TIMEOUT_SECONDS`, default `120s`). | **Observed** live during this engagement, end-to-end through the real API (not mocked), on CPU-only reference hardware with `llama3.2:3b`: plain chat ~64s; Ship 30 essay ~78-273s depending on target length and machine; HTML artifact ~121-198s. Full-length generation routinely exceeds 120s, which is why 120s is a **soft** budget (streamed, returns partial-but-coherent content) rather than a hard cutoff -- see 2.5's latency trade-off and `agent_transcripts/13`. |
| 4 (operational) | **Automated Test Pass Rate** | Proportion of the automated test suite that passes without modification. | Proposed target: 100% of tests not gated by an unavailable external dependency. | **Observed**: 38/38 pure-Python and mocked-boundary tests pass (`pytest backend/tests`). An additional 25 API-level tests exist and are written to run against a real Postgres+pgvector instance; they are designed to skip cleanly (not fail, not silently pass) when no test database is configured — see `backend/tests/conftest.py`. |

## 2.3 Assumptions

The assignment leaves some of these gaps by design (it's a take-home, not a
full client discovery process) — no interviews or user research were
conducted for this brief; these are engineering/product assumptions made to
resolve ambiguity, not findings.

1. **The internal product/growth team is the sole intended audience, not a
   public or external one.**
   *Why necessary:* the assignment describes an internal assistant for that
   team, but doesn't specify an access boundary.
   *Decision it affects:* no public-facing authentication was built; CORS
   defaults to localhost dev origins; the deployment story targets a single
   internal instance, not a multi-tenant or public one.

2. **The transcript archive is the sole authoritative knowledge source —
   answers should not rely on the model's own unsupported general knowledge
   for product/growth questions.**
   *Why necessary:* "grounded answers" is stated as a requirement, but the
   assignment doesn't define what should happen when the archive doesn't
   cover a topic.
   *Decision it affects:* the retriever enforces a hard cosine-similarity
   floor (`RAG_MIN_SIMILARITY`, default 0.30) and the generator returns a
   fixed, deterministic "not grounded" message with **no LLM call at all**
   when nothing clears it, rather than letting the model answer from its own
   training data.

3. **Users may ask follow-up questions within the same session** (this is a
   conversational tool, not strictly single-shot Q&A).
   *Why necessary:* the assignment asks for grounded answers and reusable
   written content without specifying whether interaction is one question
   per request or an ongoing conversation.
   *Decision it affects:* sessions and messages are persisted in Postgres,
   and recent prior turns are included as context on follow-up questions.

4. **This is an internal tool for the duration of this engagement, not a
   production, internet-scale product.**
   *Why necessary:* no traffic volume, SLA, or scaling requirement is given.
   *Decision it affects:* deployment is a single-instance Docker Compose
   stack (or manual local run); no load balancing, autoscaling, or
   multi-region design was attempted.

5. **Anonymous, internal user metadata is sufficient unless the client
   specifies authentication requirements.**
   *Why necessary:* the assignment implies "user metadata" should persist
   alongside sessions, but says nothing about login or identity.
   *Decision it affects:* `ChatSession.client_label` is an optional, freeform
   anonymous label (e.g. a browser user-agent string) — not a user account —
   and no login flow was built.

6. **Ollama is required for the evaluator's local demo; cloud LLM support
   exists as an additional provider, not the only model path.**
   *Why necessary:* the assignment states a local model is mandatory for the
   demo, while also implying value in a cloud option (for quality/
   reliability comparison).
   *Decision it affects:* `app/llm/router.py` always tries Ollama first and
   only falls back to OpenAI on failure (or on an explicit per-request/
   env-level override) — the system must work correctly with zero cloud
   configuration at all.

7. **The Claude Agent SDK's required role is best satisfied by intent
   routing, not final answer generation.**
   *Why necessary:* the assignment requires building an agent layer with the
   Claude Agent SDK, which is cloud-only (it shells out to the `claude`
   CLI). Using it to write final answers would make every successful
   request silently cloud-generated, which would make the "local model
   mandatory" requirement impossible to actually verify.
   *Decision it affects:* the SDK is used only to classify a message's
   intent (chat / essay / HTML artifact) in `app/agent/orchestrator.py`;
   every generation path still flows through the same Ollama-first router
   regardless of whether the SDK is enabled.

## 2.4 Scope Choices

### In Scope

- Grounded conversational Q&A over the full transcript archive, with
  per-answer source citations (episode, guest, similarity score, URL).
- Transcript ingestion (chunking + local embedding) and pgvector-based
  retrieval, with a hard relevance floor rather than always returning the
  nearest neighbors regardless of relevance.
- Source attribution surfaced in every grounded response — not a "click to
  expand" afterthought.
- Multi-turn session context, persisted in Postgres.
- The Ship 30 for 30 essay-writing skill.
- Markdown and HTML/CSS artifact generation.
- An in-app, sandboxed Artifact Viewer for rendering generated Markdown/HTML.
- Dual LLM configuration (local Ollama default/required, cloud OpenAI
  fallback) plus a per-request provider override in the UI.
- An agent layer (Claude Agent SDK) for intent classification, with a
  deterministic offline fallback when the SDK is unavailable.
- PostgreSQL + pgvector persistence for sessions, messages, and transcript
  chunks, with automatic schema creation on startup.
- Observability/resilience: structured logging, a multi-component health
  endpoint, graceful degradation on DB/model failures.
- Automated tests (pure-Python/mocked-boundary and API-level) and
  documentation (README, architecture doc, this PRD).

### Explicitly Out of Scope

- **Full enterprise authentication/SSO** — not required by the assignment;
  an anonymous, internal-tool session model satisfies the stated need
  without inventing an identity system to evaluate.
- **Multi-tenant architecture** — a single internal team is the described
  audience; tenant isolation adds real complexity with no corresponding
  requirement.
- **Production-scale distributed infrastructure** (load balancers,
  autoscaling, multi-region) — the assignment frames this as a local/demo
  deployment; a single-instance Docker Compose stack matches that scope.
- **Fine-tuning a foundation model** — the assignment's grounding mechanism
  is retrieval (RAG), not model customization; fine-tuning would add
  significant cost and complexity while addressing a problem RAG already
  solves here.
- **Complex analytics dashboards** — the assignment asks for a health
  endpoint, not usage analytics; a dashboard would be speculative scope.
- **Mobile-native applications** — the assignment describes a web assistant;
  a responsive web UI covers the stated use case without a second platform.
- **Arbitrary external web research** by the agent — letting the agent fetch
  the open web would directly undermine assumption 2 (the transcript
  archive as the sole authoritative source) and the "reliable, grounded"
  requirement itself.
- **A live/scheduled transcript refresh pipeline** — one-time ingestion is
  sufficient to demonstrate the full ingestion → retrieval → grounding
  pipeline; a refresh job is an operational concern orthogonal to what's
  being evaluated here.

### Scope Rationale

Every inclusion above either directly satisfies an explicit assignment
requirement (grounded Q&A, the two writing skills, dual-provider LLM
config, the agent layer, persistence, health/observability) or is required
for those to actually work end-to-end (ingestion, retrieval, the sandboxed
viewer). Every exclusion trades away complexity that a real production
rollout would eventually need, but that this engagement's timeline and
evaluation criteria don't call for — an evaluator judging this take-home is
assessing whether the core grounded-assistant loop works reliably and
whether the trade-offs were made deliberately, not whether it's ready to
onboard a second team. Where a cut corner remains a real risk (see below),
it's called out rather than hidden.

## 2.5 Risks and Trade-offs

| Risk / Trade-off | Impact | Mitigation | Residual Risk |
|---|---|---|---|
| **Hallucination / unsupported answers** | Model states something as fact that isn't actually supported by the retrieved context, undermining trust in every answer. | Grounding is enforced both structurally (similarity floor + no-LLM-call short-circuit) and by system-prompt instruction requiring citation from the provided context only. | A model can still misattribute or overstate *within* material that did clear the relevance floor — citations reduce but don't eliminate this. |
| **Retrieval quality** | A relevant chunk exists but scores just under the similarity floor (or an irrelevant chunk scores just above it), producing a wrong grounded/not-grounded call. | `RAG_MIN_SIMILARITY` is a tunable env var, and `backend/scripts/probe_retrieval_threshold.py` gives a repeatable way to characterize any candidate value against the real corpus before changing it — used to measure the current behavior (below), not just guess. | **Measured, not hypothetical:** topics adjacent to but not covered by the corpus (personal taxes, choosing a programming language) score 0.32-0.46 — the *same* band as some genuinely in-domain, plainly-phrased questions ("Is it better to raise a big round or stay lean?" scores 0.28-0.32; "What did guests say about burnout?" scores 0.40-0.44). Raising the floor to reject the former would reject the latter too (verified: a 0.45 floor drops the burnout example to 0 retrieved chunks). Kept at 0.30 deliberately — the system prompt's grounding instruction is the second line of defense for this band, and was observed in practice to correctly decline to answer from weak context even when the floor let it through. |
| **Latency vs. ideal essay length** | CPU-only local inference for long-form skills (essay, HTML artifact) routinely takes well over a minute, and live measurement showed it can exceed 3 minutes for a full ~1,250-word essay. Forcing the model to always reach that length would make the mandatory local demo unpredictably slow. | **Deliberate trade-off, not a guess:** `OLLAMA_TIMEOUT_SECONDS` (`120s`) is a soft wall-clock budget -- the response is streamed and, if the budget runs out, whatever coherent content was generated so far is returned (trimmed cleanly) rather than discarded or force-completed. The Ship 30 prompt itself ranks groundedness/coherence above exact word count and explicitly forbids padding (`app/skills/ship30.py`). Automatic OpenAI fallback exists when configured, and isn't bound by this machine's CPU throughput. | A locally-generated essay is often shorter than the ~1,250-word ideal on CPU-only hardware -- this is accepted by design, not hidden. If a cutoff produces too little content to be useful at all (not just short), that's still treated as a failure with a clear timeout message, not a silent near-empty response. |
| **Cloud LLM cost** | Falling back to OpenAI on every local hiccup could become expensive at higher query volume. | Fallback only triggers on Ollama failure/timeout, not on every request; acceptable given this engagement's low, non-production query volume. | Cost was not load-tested; no per-request budget or rate limit is enforced. |
| **Local Ollama model quality** | A small local model (`llama3.2:3b`, chosen for CPU latency) will produce shallower or less precise answers than a larger cloud model. | The cloud fallback (and the manual provider toggle) exists specifically so quality can be compared against a larger model when desired. | The mandatory local-only demo path is, by definition, running the weaker of the two models. |
| **Data leakage / secrets** | Transcript content and user questions sent to OpenAI (fallback) or Anthropic (agent routing, when enabled) leave the local machine; a leaked `.env` would expose API keys and the DB connection string. | `.env` is gitignored; a full git-history secret scan found no committed `.env` or key-shaped strings. Cloud calls are opt-in (`OPENAI_API_KEY`/`AGENT_SDK_ENABLED`), not mandatory. | Acceptable for this engagement since transcripts are already public podcast content — this would need re-evaluating for any genuinely private corpus. |
| **Unsafe HTML artifact rendering** | An LLM-generated HTML document is, functionally, unreviewed third-party content — it could contain a script attempting to steal cookies/session data if rendered naively. | Two independent layers: a server-side sanitizer strips `<script>` tags, inline event handlers, and `javascript:` URLs; the frontend then renders the (already-sanitized) HTML inside a sandboxed `<iframe>` with `sandbox="allow-scripts"` and **no** `allow-same-origin`, so even a sanitizer bypass has no access to the parent page's cookies or storage. The sandbox, not the sanitizer, is the real trust boundary. | No client-side sanitizer (e.g. DOMPurify) is used as a third layer — judged redundant given the sandbox already blocks the realistic attack surface for this scope. |
| **Database failure / unreachable** | Retrieval, session persistence, and even app startup depend on Postgres being reachable. | `/api/health` reports DB status independently; retrieval/generation failures return an actionable `502`, not a raw stack trace; schema creation is automatic and idempotent so a fresh DB doesn't require manual setup. | The app cannot start at all without a reachable DB (`ensure_schema()` runs at import time) — there is no degraded "DB-less" mode. |
| **Ollama unavailable** | The mandatory local-model path is simply down (not installed, not running, model not pulled). | `/api/health` reports Ollama status independently; automatic fallback to OpenAI when configured. | With no cloud key configured, an unavailable Ollama is a hard failure for every generation request — there is no third fallback. |
| **Model timeout** | A slow local response is indistinguishable from a hung one without a bound, and a hard cutoff would discard otherwise-useful partial output. | `OLLAMA_TIMEOUT_SECONDS` (`120s`) is a soft, streamed budget enforced by `asyncio.wait_for` around the whole read, rather than a hard cutoff or a per-chunk timeout (a per-chunk read timeout was tried first and rejected -- it misfired during Ollama's CPU-bound prompt-processing phase, before any token streams back, which can itself take a long time; see `agent_transcripts/13`). A merely-slow-but-progressing generation gets its partial output returned instead of an exception; a genuinely dead connection still fails via a generous backstop timeout. Configurable per-hardware. | Any fixed budget is a bet against variable hardware; slower machines than the reference ones used here will more often return a shorter response, or -- if that response is too short to be useful -- an actionable timeout error. |
| **Empty retrieval (out-of-domain questions)** | A question genuinely outside the corpus could either get a fabricated answer (bad) or an overly aggressive refusal on a borderline-relevant question (also bad). | The relevance floor converts "zero chunks above threshold" into a fixed, honest "not grounded" response with no LLM call — a deterministic, testable outcome either way. | The floor is a single global threshold; it doesn't adapt per topic or query type. |
| **Complexity vs. reliability** | Every additional moving part (agent SDK, dual providers, artifact skills, sandboxed viewer) is another thing that can fail. | Each subsystem degrades independently and visibly rather than taking down the whole app: agent routing falls back to a heuristic classifier, LLM generation falls back to OpenAI, `/api/health` reports each component separately. | The system has more moving parts than a minimal single-provider Q&A bot would — that complexity is deliberate (it's what the assignment asks for), but it is real surface area, not free. |

**The four-way trade-off (cloud quality vs. local availability vs. cost vs.
reproducibility):** the mandatory local-only demo path guarantees zero-cost,
zero-external-dependency reproducibility for an evaluator — anyone can run
this offline and get a real answer — but it locks in the *weakest* model in
the system for that guarantee. The cloud fallback recovers quality and
speed, but reintroduces cost and a dependency the demo is explicitly meant
to not require. This project doesn't resolve that tension (it can't — it's
inherent to "must work fully offline" plus "should also support a better
model"); it makes the trade explicit and evaluator-controllable via the
provider toggle and env configuration, rather than silently picking one side
of it.

**The HTML-artifact sandboxing trade-off:** treating every generated HTML
artifact as fully untrusted — even though it was produced by this same
application's own pipeline — is deliberately conservative. It costs some
capability (the artifact genuinely cannot do anything beyond static
markup/CSS: no scripts, no external resources, no navigation out of the
iframe), in exchange for the guarantee that a model completely ignoring its
system prompt (a realistic failure mode for a 3B local model, not a
hypothetical one) still cannot compromise the parent application. For a
feature whose entire input is "whatever the language model decided to
generate," that trade is worth making.

## 2.6 Key Product Decisions

**Decision:** Ground every answer in retrieved transcript chunks, and
short-circuit to a fixed "not grounded" message with no LLM call when
nothing clears a hard relevance floor.
**Reason:** Makes "grounded" a structural, testable property of the
pipeline instead of something that depends on a 3B local model reliably
phrasing a refusal the same way every time.

**Decision:** Use the Claude Agent SDK for intent routing only (chat vs.
essay vs. HTML artifact), never for writing the final answer text.
**Reason:** The SDK is cloud-only; using it to generate answers would make
every successful request silently cloud-generated, defeating the
assignment's mandatory local-model requirement. Routing is the genuinely
agentic part of this system that doesn't require cloud-grade prose.

**Decision:** Default to a small local model with automatic cloud fallback,
plus a per-request provider override exposed in the UI.
**Reason:** Satisfies the mandatory local-demo requirement while keeping a
credible, user-controlled path to compare against cloud quality, rather than
locking the choice into a single env variable only an operator can change.

**Decision:** Treat all LLM-generated HTML as fully untrusted — sanitize
server-side, and render only inside a sandboxed iframe with no
`allow-same-origin`.
**Reason:** The sandbox, not the sanitizer, is the actual trust boundary; a
model that ignores its own instructions (a real failure mode, not a
hypothetical) still can't reach the parent app's cookies or storage.

**Decision:** Persist sessions and messages with an optional anonymous
`client_label` instead of building authentication.
**Reason:** The assignment doesn't specify user identity requirements; an
anonymous label satisfies the "user metadata" persistence need without
scope creep into an auth system that wouldn't add evaluation value here.

**Decision:** Auto-create and additively migrate the database schema at
application startup instead of requiring a manual migration step.
**Reason:** A one-command Docker Compose deployment only actually works if
a fresh, empty database becomes usable with zero manual intervention —
otherwise the deployment requirement is documented, not delivered.

**Decision:** Make the local-model request timeout a *soft* streamed budget
(120s, enforced via `asyncio.wait_for`) rather than a hard cutoff on a
single buffered response, and set the Ship 30 essay's ~1,240-1,250-word
target as an ideal the prompt explicitly deprioritizes below groundedness
and coherence.
**Reason:** Live, end-to-end measurement showed full-length generation on
CPU-only hardware routinely exceeds two minutes; a hard cutoff at any fixed
value would either fail the mandatory local-only demo constantly (a short
value) or make it unusably slow (a long one). Streaming lets a cutoff return
whatever coherent content was generated instead of discarding it — a
shorter-than-ideal local essay is accepted by design, not silently forced
to be shorter, so quality and groundedness within the runtime budget
outrank hitting an exact word count. See `docs/architecture.md`'s "Ship 30
for 30 length vs. local-model latency" section and `agent_transcripts/13`
for the full mechanism and the live measurements behind it (an earlier
120s value using a hard per-chunk timeout was tried and rejected during
this same investigation before the streaming/soft-deadline redesign,
documented there rather than silently dropped).

**Decision:** Parse transcripts into whole speaker turns (using the
corpus's own `Speaker (HH:MM:SS):` markers) and chunk on turn boundaries
with real per-chunk timestamps, falling back to the original raw
character-based split only for the small number of transcripts that don't
use this format.
**Reason:** The source data already carried the structure needed to fix two
audit-flagged gaps at once (chunking could split mid-sentence; `timestamp`
was schema-supported but never populated) — using it was strictly better
than either leaving both gaps or inventing a synthetic chunking scheme.
Kept a fallback rather than requiring every transcript to match, since 2 of
303 files use different, one-off formats.

## 2.7 Implementation Plan

Built in dependency order — each phase needed the previous one working
before it could be verified against a real system rather than mocks:

1. **Foundation:** FastAPI skeleton, Postgres schema (`sessions`,
   `messages`, `transcript_chunks` with pgvector), and session
   create/persist endpoints. Nothing downstream (retrieval, generation,
   agent routing) is testable without a real session and a real database to
   persist against.
2. **Knowledge base:** transcript ingestion (`scripts/ingest.py`) — chunking,
   local embedding, storage — verified against the real corpus before any
   retrieval logic was written on top of it.
3. **Grounded Q&A core:** the retriever (similarity floor, top-k), the
   Ollama/OpenAI dual-provider router, and the plain chat endpoint. This is
   the assignment's central requirement (§4.1) and the dependency every
   other product task builds on.
4. **Agent layer:** Claude Agent SDK intent routing (chat vs. essay vs.
   HTML artifact) added once plain grounded chat was already working, so
   routing failures could be isolated from generation failures.
5. **Content skills:** Ship 30 for 30 essay generation, then the HTML
   artifact skill (sanitizer + sandboxed iframe) — built as dedicated
   modules with their own prompts, not branches inside the chat handler, so
   each has an independently testable contract.
6. **Frontend:** chat UI, source cards, provider toggle, artifact viewer —
   built against the already-working backend endpoints rather than in
   parallel with them, so the UI was always integrating against real
   responses, not a hypothetical API shape.
7. **Deployment packaging:** Docker Compose (backend, frontend, db),
   `.env.example`, health checks — done once the manual (non-Docker) path
   was already fully working, so containerization failures were isolated
   from application-logic failures.
8. **Hardening pass:** the items in `agent_transcripts/` — timeout tuning
   from live measurement, the RAG grounding structural fix, accessibility
   audit, and the Ship 30 length/latency trade-off — represent a deliberate
   verification phase against the *real* running system (not mocks) after
   the core build was feature-complete, on the premise that an evaluator
   will also run the real system, not just read the code.

This order is why `agent_transcripts/`' numbering looks iterative/debugging-driven
rather than a clean waterfall — most of the individually-numbered transcripts
are corrections found during phase 8, applied back into earlier phases.
