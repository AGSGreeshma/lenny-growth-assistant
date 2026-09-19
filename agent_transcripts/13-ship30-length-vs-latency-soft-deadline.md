# Agent Transcript 13 — Ship 30 for 30 Length vs. Local-Model Latency: a Soft-Deadline Trade-off

## Problem

The assignment wants the Ship 30 for 30 essay at ~1,250 words. A prior
session (see `09-ollama-timeout-tuning-from-live-measurement.md`) had already
raised `OLLAMA_TIMEOUT_SECONDS` from 60s -> 180s -> 300s based on live
measurement showing full-length generation on CPU-only hardware routinely
exceeds two minutes. Two live test runs earlier in *this* session (before
any of the changes below), with a prompt already pushing for length,
measured:

- 557 words in 193s
- 826 words in 273s

Both already past even the 180s value the project had previously rejected
as too tight for the HTML-artifact skill.

The instruction for this pass was explicit: keep the Ship 30 word count as
an *ideal* target, but set the generation timeout to exactly 120 seconds,
framed as a deliberate engineering trade-off (shorter-but-complete response
over an exact word count) rather than an accidental limitation.

## Investigation

Read `agent_transcripts/09` before touching anything: 120s had already been
tried on this exact project and had *failed* -- the HTML-artifact skill
timed out at 121s, which is why the timeout was raised to 180s in the first
place, then to 300s after a CPU-fallback measurement (driver/CUDA issue --
see `docs/architecture.md`) came in even higher (198.6s essay, 180.5s
HTML-artifact).

Combined with this session's own 193s/273s measurements, the conclusion was
unavoidable: at this machine's measured throughput (~2.9-3 words/sec), 120s
buys roughly 350 words. With the *original* non-streaming `OllamaClient`
(`stream: false`, a single buffered request), a hard 120s `httpx` timeout
on a request that isn't done by then raises an exception and discards
*everything* generated so far -- not "a shorter response," but zero content.
Setting the number to 120 without changing that mechanism would make the
mandatory local Ollama demo return a timeout error on essentially every
Ship 30 / HTML-artifact request on this hardware.

This was surfaced to the user directly, with three explicit options: accept
frequent timeouts as-is (viable only if the real demo/recording machine is
faster than this one), keep a higher empirically-validated ceiling instead
of literally 120, or implement a streaming soft deadline that actually
returns partial-but-coherent content instead of failing. The user chose the
streaming soft-deadline approach -- the only one of the three that
implements "the response may be shorter, but should still be useful" as an
actual mechanism rather than an aspiration.

## Fix

1. **`app/llm/ollama_client.py`**: switched from a single buffered
   `stream: false` request to `stream: true`, reading Ollama's NDJSON
   response line-by-line and accumulating `message.content` as it arrives.
   The wall-clock budget is enforced with `asyncio.wait_for` wrapped around
   the entire read (not a per-chunk `httpx` read timeout -- see
   Verification below for why that first attempt was wrong); on
   cancellation, whatever content had already been accumulated is trimmed
   back to the last clean sentence ending (`_trim_to_sentence_boundary`) and
   returned with `hit_deadline=True`, instead of being discarded. The
   underlying `httpx` timeout is deliberately generous
   (`timeout_seconds + 60s`) -- it exists only as a last-resort backstop
   against a connection that never sends anything at all; `asyncio.wait_for`
   is what actually enforces the budget in the normal case.
2. **`app/llm/router.py`**: added `GenerationTimeoutError` (a distinct
   `RuntimeError` subclass) and a `_MIN_USEFUL_WORDS` (60) floor. A
   deadline cutoff with substantial content is a normal successful
   response; a cutoff that produced too little to be useful is treated like
   any other failure -- falls back to OpenAI if configured, otherwise
   raises `GenerationTimeoutError` with a clean, actionable message quoting
   the actual configured limit.
3. **`app/api/chat.py` / `essay.py` / `artifact.py`**: catch
   `GenerationTimeoutError` ahead of the generic exception handler and
   return `504` with that message directly, instead of the generic `502`
   used for other generation failures.
4. **`app/skills/ship30.py`**: rewrote the system prompt around an explicit
   priority order (groundedness > relevance > coherent narrative > useful
   takeaways > structure > reasonable length > exact word count) and told
   the model directly not to pad toward 1,250 words. This also fixed an
   unrelated defect noticed while re-reading the previous session's
   prompt change: a "Mechanism / Example / How to apply it" bullet
   structure had been invented to force longer sections, and the "Example"
   slot was observed inventing specific company names (PayPal, Dropbox,
   Twilio) that were not actually in the retrieved transcript chunks --
   a real hallucination risk. The rewritten prompt explicitly forbids
   naming any company/product/case study not present in the provided
   source text.
5. **`app/config.py` / `.env.example` / `docker-compose.yml`**: default
   `OLLAMA_TIMEOUT_SECONDS` changed 300 -> 120, with the comment rewritten
   to describe the soft-deadline semantics and explicitly flagged as an
   engineering decision, not a guess.
6. Updated every stale reference to the old timeout values and the
   unconditional "~1,250 words" framing across `README.md`, `docs/PRD.md`,
   and `docs/architecture.md` (a new "Ship 30 for 30 length vs.
   local-model latency" section), and added a clarifying note to
   `FINAL_REQUIREMENTS_AUDIT.md`'s chronological fix #7 rather than
   silently rewriting that historical entry.

## Verification

- Full non-DB test suite (57 tests) passes; `test_router_fallback.py` was
  rewritten for the new `(content, hit_deadline)` return contract and
  extended with soft-deadline cases (substantial content returned normally,
  too-short content falls back / raises `GenerationTimeoutError`), and a new
  `test_ollama_client.py` exercises the streaming cutoff and
  sentence-boundary trimming against a mocked NDJSON transport with real
  (short) delays -- no mocked clock, no real network.
- The DB-backed API suite (81 tests, 1 pre-existing failure unrelated to
  this work -- `test_artifact_rejects_empty_topic`, a pre-existing
  schema-validation-order issue not touched by this change) was run against
  a genuinely disposable `lenny_test` database, per the README's own
  warning -- see the incident below for why that warning is there.
- **Real, live end-to-end verification against the actual running Ollama
  instance** (not just unit tests) found two real bugs the mocked tests
  could not have caught, both fixed and re-verified live afterward:
  1. **The first streaming implementation used a 30s per-chunk `httpx` read
     timeout as a "stall guard."** Live testing showed this firing at ~38s
     with a real 502, *before any token had streamed back at all* -- Ollama
     was still processing the large RAG prompt (prefill), which took longer
     than 30s on CPU, and a per-chunk timeout can't distinguish "no bytes
     yet because still computing" from "actually hung." Fixed by replacing
     the per-chunk timeout with `asyncio.wait_for` around the whole read,
     which measures true total elapsed time regardless of which phase it's
     in. Re-verified live: a real `/api/essay` call returned `HTTP 200`,
     `provider: "ollama"`, 93 words, at 120.3s wall-clock.
  2. **The sentence-boundary trimmer initially left a dangling list marker**
     (`"...effective.\n\n**1."`) at the end of a cutoff response, because a
     bare `[.!?]` regex treated the period in a numbered-list marker as a
     valid sentence ending. Fixed by requiring at least two letters
     immediately before the punctuation. Re-verified live: a second real
     `/api/essay` call returned 443 words ending cleanly on a complete
     sentence, at 120.4s wall-clock.
- **Incident during this verification, disclosed here because it happened
  in the course of this exact work:** an earlier verification step ran
  `pytest` with `TEST_DATABASE_URL` pointed at `localhost:5432/lenny` --
  the *same* database Docker Compose uses for real data, not a separate
  test database -- which the README explicitly warns against, since the
  test fixtures delete all rows from every table after each test. This
  wiped the full ingested transcript corpus (10,246 chunks) and all prior
  session history. It was caught immediately (an essay request that should
  have returned real sources came back with the structural "not grounded"
  message instead), disclosed, and fully recovered by re-running
  `scripts/ingest.py` against the same corpus still present on disk (chunk
  count matched exactly: 10,246). No data was permanently lost, but it's
  documented here as a real mistake, not smoothed over -- and is the reason
  the DB-backed suite above was re-run against a disposable `lenny_test`
  database instead.

## Lesson

A number given as an instruction ("set the timeout to 120s") and a number
already disproven by this same project's own prior measurement
(`agent_transcripts/09`) can both be true at once -- the right response
wasn't to silently comply (which would have shipped a demo that fails on
its own mandatory path) or to silently override the instruction, but to
surface the conflict with the actual evidence and let the trade-off be
chosen explicitly. The streaming soft-deadline mechanism is what actually
makes "120 seconds, and a shorter response is fine" true simultaneously,
instead of just documenting an aspiration that the non-streaming client
couldn't have delivered.
