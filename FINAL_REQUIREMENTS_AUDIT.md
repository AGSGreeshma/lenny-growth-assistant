# Final Requirements Audit — The Lenny Growth Assistant

**Scope of this document:** this audits the project against **Section 3 —
Core Requirements** of the Forward Deployed Engineer take-home assignment,
as those 16 requirements were provided verbatim during this engagement. It
does not claim coverage of sections of the assignment brief that were never
supplied to this session in full text — where the assignment's other
sections were referenced only indirectly (e.g. via the PRD or prior
handoff notes), that is noted explicitly rather than assumed.

**How this document was produced:** every finding below was either
(a) directly observed by running the actual application, real Ollama, and a
real Postgres database during this engagement, or (b) confirmed by reading
the relevant source file. Nothing here is inferred from documentation
alone. Where something could not be verified in this environment, that is
stated as a limitation, not glossed over. This document reflects the
**current** state of the code, after the fixes described in §3 — it
supersedes the in-chat audit delivered earlier in this engagement, which
captured a snapshot *before* those fixes.

---

## 1. Executive Summary

Every one of the 16 Section 3 requirements has a real, working
implementation. The initial audit (delivered mid-engagement, before the
fixes in §3 below) found the core request/response/session/grounding loop
fully working end-to-end, plus a set of concrete, real gaps in the
ingestion/indexing/traceability layer and one external blocker (no OpenAI
credits). All of the concrete, fixable gaps have since been fixed and
re-verified; the external blocker remains and is documented, not hidden.

**Fully implemented and verified, live, through the real running app:**
FastAPI backend; the Claude Agent SDK genuinely routing a real request
(`used_agent_sdk: true` and `provider: "ollama"` observed in the *same*
response); session creation, isolation (Session B provably cannot see
Session A's history), and persistence across a full backend process
restart; PostgreSQL storage of conversations/session IDs/timestamps/user
metadata; request validation and structured errors; the multi-component
`/api/health` endpoint; env-driven provider configuration with a working
per-request override and automatic Ollama→OpenAI fallback (proven by
forcing a real Ollama failure and watching it correctly reach OpenAI); the
mandatory Ollama-only path (verified with `OPENAI_API_KEY` and
`ANTHROPIC_API_KEY` both genuinely absent); the full transcript archive
ingested (303 episodes, 10,246 chunks); structural grounding (a hard
similarity floor plus a no-LLM-call short-circuit when nothing clears it);
and Docker Compose, verified end-to-end including on a from-scratch
database.

**Fixed since the original audit (see §3 for detail):**
- The HNSW vector index is now created automatically by the app's own
  startup code, not only by a separate manual SQL script — verified on a
  genuinely fresh database via `docker compose up`.
- Re-ingestion is now idempotent (skips already-ingested episodes; a
  `--force` flag exists for intentional re-embedding) — verified by running
  ingestion twice against a fully-populated database and confirming zero
  new/duplicate chunks.
- Chunking is now turn-aware (splits on real speaker-turn boundaries
  instead of raw character counts) and populates real per-chunk timestamps
  for 99%+ of the corpus, surfaced in the UI as a clickable deep link to
  the exact moment in the source video.
- A prompt-design bug that caused some grounded, correctly-cited answers
  to also contradict themselves with "the transcripts don't provide enough
  information" was found, root-caused, and fixed — verified via a
  controlled A/B test and a live retest through the real running app.
- An accessibility pass fixed a real structural gap (the app had no
  `<h1>` once a conversation started) and five interactive controls
  missing the focus-visible style used everywhere else in the app.

**Still open (external, not a code gap):** the configured OpenAI API key
authenticates correctly but the account has zero credits (confirmed via a
real network call that returned OpenAI's own `insufficient_quota` error).
The cloud fallback path is code-complete and was proven to correctly
*attempt* the fallback (a forced Ollama failure genuinely reached OpenAI's
servers) — it simply cannot complete a real cloud answer until the account
has credits. This is the one requirement not independently resolvable
without the account owner's action.

**Not independently re-verifiable in this environment:** the live proof
that the Claude Agent SDK genuinely routes a real request only worked
because this specific machine has Claude Code's own bundled `claude.exe`
ambiently reachable — not because the project's own documented setup
(`npm install -g @anthropic-ai/claude-code` + `ANTHROPIC_API_KEY` in
`.env`) was followed independently. The routing logic and its offline
fallback are both real and correctly implemented; whether the *documented*
setup path reproduces the same result on a genuinely clean machine was not
tested, since no such machine was available during this engagement.

---

## 2. Requirement Matrix (current state)

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | FastAPI | ✅ COMPLETE | `app/main.py`; 4 routers; started and responded to `/api/health` repeatedly, including inside Docker |
| 2 | Agent Integration (Claude Agent SDK) | ✅ COMPLETE | Live `/api/chat` call returned `used_agent_sdk: true` and `provider: "ollama"` in the same response — proves the real routing→retrieval→Ollama→response chain in one pass. Caveat: verified via this machine's ambient `claude.exe`, not the documented independent setup (see §1) |
| 3 | Session Handling | ✅ COMPLETE | Live: created Session A & B, sent messages to A, confirmed B's history is `[]`; follow-up context proven (an answer referenced content only present in an earlier turn); A's history survived a full backend process restart |
| 4 | PostgreSQL Persistence | ✅ COMPLETE | See checklist below |
| 5 | API Quality | ✅ COMPLETE | Live-tested 422 (missing field / invalid UUID / over-length message), 404 (unknown session), 400 (empty message); `/api/health` reports db/ollama/embedding_model independently plus a rollup |
| 6 | Provider/Model Configuration | ✅ COMPLETE | `OLLAMA_MODEL`/`OLLAMA_BASE_URL`/`OLLAMA_TIMEOUT_SECONDS`/`FORCE_LLM_PROVIDER` all env-driven; per-request `provider` override live-tested |
| 7 | Cloud LLM (OpenAI) | 🟡 PARTIAL | Code correct, real auth confirmed via a genuine network call; account has zero credits (`insufficient_quota`). External blocker, not a code defect |
| 8 | Ollama / Local LLM | ✅ COMPLETE | `llama3.2:3b`; live-verified across chat/essay/HTML-artifact, with cloud keys genuinely absent, and combined with real Agent SDK routing in one request |
| 9 | Provider Toggle / Visibility | ✅ COMPLETE | UI toggle in `Header.jsx`; `provider` always present in API responses and shown as a badge; fallback live-proven (forced Ollama failure genuinely reached OpenAI) |
| 10 | Lenny Transcript Data Source | ✅ COMPLETE | `lennys-podcast-transcripts/episodes/`, 303 episodes; fully ingested — 10,246 chunks confirmed via live DB query, into both the original Supabase instance and the Docker Compose database independently |
| 11 | Ingestion Pipeline | ✅ COMPLETE (was 🟡) | HNSW index gap fixed — `ensure_schema()` now creates it; verified on a from-scratch Docker Compose database |
| 12 | Chunking | ✅ COMPLETE (was 🟡) | Turn-aware chunking on 301/303 transcripts (character-based fallback for the other 2, by design); real per-chunk timestamps on 10,182/10,246 chunks |
| 13 | Indexing / Vector Search | ✅ COMPLETE (was ⚠️) | Index gap fixed (see #11). Similarity floor (0.30) investigated with a purpose-built diagnostic script against the real corpus; kept deliberately rather than raised, because raising it was shown to reject legitimate in-domain questions (documented with real measured scores in `app/rag/retriever.py` and `docs/PRD.md`) |
| 14 | Refresh / Re-ingestion | ✅ COMPLETE (was 🟡) | Re-running ingestion now skips already-ingested episodes; live-tested by running it twice against a fully-populated database — 0 new chunks, count unchanged |
| 15 | Source Traceability | ✅ COMPLETE (was 🟡) | Real timestamps now populate `Source.timestamp`; `SourceCard.jsx` displays them and deep-links (`&t=Ns`) to the exact moment in the YouTube video |
| 16 | Grounded Answers | ✅ COMPLETE (was ✅ with a caveat) | Full flow live-verified end-to-end. A real bug where correctly-grounded answers still self-contradicted with "not enough information" was found, root-caused to a now-redundant system-prompt instruction, and fixed — verified via a controlled A/B test and a live retest |

### Requirement 4 — PostgreSQL Persistence detail

| Data | Implemented? | Where? | Verified? |
|---|---|---|---|
| Conversations | ✅ | `ChatMessage` model, `messages` table | ✅ Live: full message history persisted, correctly ordered, survived a backend restart |
| Session IDs | ✅ | `ChatSession.id`, UUID primary key | ✅ Live: distinct real UUIDs, independently retrievable and isolated |
| Timestamps | ✅ | `created_at`/`updated_at`, `server_default=func.now()` | ✅ Live: real ISO timestamps on every message |
| User metadata | ✅ | `ChatSession.client_label`, optional freeform string | ✅ Live: created with real labels, correctly echoed and persisted |

---

## 3. Fixes Applied This Engagement (chronological)

1. **Backend dependency corruption** (environment issue, not a requirement gap) — the original venv had corrupted numpy/torch/scipy installs (likely an interrupted original install); recreated cleanly.
2. **Missing/incomplete test coverage** — added `test_retriever_threshold.py`, `test_schemas.py`, and 5 API-level test files (`test_api_sessions.py`, `test_api_chat.py`, `test_api_essay.py`, `test_api_artifact.py`, `test_api_health.py`), mocking LLM/retrieval calls. Current suite: **38 passed, 25 skipped** (skips are the DB-dependent API tests when no disposable test database is configured — by design, not a failure).
3. **`AnswerContent.jsx`** rewritten to use `react-markdown` + `remark-gfm`.
4. **Provider toggle** — added a real per-request `provider` override threaded through `generate_with_fallback()`, plus the UI control.
5. **Not-grounded visual state**, **artifact/intent wiring** from `/api/chat` responses to the frontend.
6. **Docs cleanup** — deduplicated `docs/PRD.md` (it was literally duplicated with contradictory facts), renamed/rewrote `docs/architecture.md`, removed dead `/ask` references, rewrote `README.md`.
7. **Ollama request timeout** raised from a guessed 60s (which failed real requests) to a measured 180s, based on live timing across all three generation paths.
8. **HNSW index auto-creation** — `ensure_schema()` now creates the vector index itself; verified on a genuinely fresh database.
9. **Ingestion idempotency** — episodes already ingested are now skipped by default; `--force` re-embeds intentionally.
10. **RAG similarity-floor investigation** — built `backend/scripts/probe_retrieval_threshold.py`, a reusable diagnostic tool; measured real scores across in-domain/borderline/out-of-domain queries; kept the floor at 0.30 with the reasoning documented in code and in the PRD, rather than raising it based on a single example.
11. **Turn-aware chunking + real timestamps** — rewrote `scripts/ingest.py`'s chunking to split on real speaker-turn boundaries using the corpus's own `Speaker (HH:MM:SS):` markers; caught and fixed a real regex bug along the way (`\s*` vs `[ \t]*` crossing line boundaries); re-ingested both the original and Docker databases; wired the frontend to display and deep-link timestamps.
12. **Docker Compose**, from not-installed to fully verified: installed WSL2 and Docker Desktop; fixed a CPU-only-torch install issue (was about to pull several GB of unneeded CUDA packages on Linux); worked through two transient network failures; fixed a frontend healthcheck bug (IPv4 vs. IPv6 `localhost` resolution); ingested the full transcript archive into the Docker database independently; verified a real grounded, cited answer through the fully containerized stack.
13. **Hedging-answer prompt bug** — found live (answers that cited real sources but still claimed insufficient information), root-caused to a system-prompt instruction made redundant by the similarity-floor fix in #10/#8, fixed and verified via A/B test plus a live retest through the real app.
14. **Accessibility pass** — added the page's only `<h1>` (previously absent once a conversation started), visible focus states on 5 controls that had none, a landmark role + Escape-to-close on the artifact viewer, and several smaller label/description fixes.

---

## 4. What Remains

1. **OpenAI credits** — external, requires the account owner to add credits. Not blocking the mandatory local-only demo path.
2. **Agent SDK independent-environment verification** — the routing logic and offline fallback are both correctly implemented and were exercised live, but only via this machine's ambient Claude Code installation. Re-testing on a genuinely clean machine (only the documented `npm install -g @anthropic-ai/claude-code` + `ANTHROPIC_API_KEY` setup) was not possible in this environment.
3. **No automated accessibility testing** (e.g. axe-core) in the test suite — the accessibility pass in this engagement was manual code review plus a rendered-DOM check, not an automated regression guard.
4. **Nothing in this repository has been committed to git during this engagement** — all changes described above exist as uncommitted working-tree changes. This is a process note, not a functional gap.

---

## 5. Verification Commands

```bash
# Backend tests
cd backend && venv\Scripts\activate && pytest tests -v
# Expect: 38 passed, 25 skipped

# Docker Compose, full stack
docker compose up --build
# Expect: db, backend, frontend all "healthy"
curl http://localhost:8000/api/health
# Expect: "status": "healthy"

# Ollama-only path (no cloud keys)
# unset OPENAI_API_KEY / ANTHROPIC_API_KEY before starting the backend, then:
curl -X POST http://localhost:8000/api/sessions -d '{}'
curl -X POST http://localhost:8000/api/chat -d '{"session_id":"<id>","message":"How should a startup find product-market fit?"}'
# Expect: "provider": "ollama", "grounded": true, real sources with real timestamps

# Retrieval threshold diagnostic
cd backend && python scripts/probe_retrieval_threshold.py

# Ingestion idempotency
python scripts/ingest.py        # second run: "Episodes skipped (already ingested): 303"
python scripts/ingest.py --force  # forces re-embedding
```

---

## 6. Final Verdict

**READY**, with two explicitly-documented, non-blocking exceptions: OpenAI
credits (external, doesn't affect the mandatory local-only path) and
independent-environment Agent SDK re-verification (the implementation is
correct and was proven live; only the specific clean-machine reproduction
step is untested). Every requirement that could be verified end-to-end in
this environment was verified end-to-end, not inferred from code reading
alone — including deliberately adversarial checks (forcing Ollama to fail
to prove the fallback really triggers, running ingestion twice to prove
idempotency, testing on a from-scratch database to prove the schema
bootstrap is genuinely automatic).
