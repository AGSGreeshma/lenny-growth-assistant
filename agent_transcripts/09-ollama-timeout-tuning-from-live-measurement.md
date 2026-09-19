# Agent Transcript 09 — Tuning the Ollama Timeout from Live Measurement, Not Guessing

## Problem

`OllamaClient`'s default request timeout was 60 seconds. During live,
end-to-end verification of the Ollama-only path (real backend, real Ollama,
real Postgres, `OPENAI_API_KEY` cleared), a genuinely grounded `/api/chat`
question failed with a 502:

```
WARNING:lenny-assistant:Ollama failed () -- falling back to OpenAI
RuntimeError: Ollama failed and OPENAI_API_KEY is not configured.
```

The empty `()` in the warning (an exception whose `str()` is empty) is the
signature of an `httpx` read-timeout raised by the underlying `httpcore`
transport with no message attached — not a connection error, not a 4xx/5xx
from Ollama itself.

## Investigation

Measured, rather than guessed:

1. A trivial prompt ("say hello") round-tripped through raw Ollama in
   `0.8s` — the model and server were healthy; this wasn't a broken
   installation.
2. A prompt sized like a real chat request (full system prompt + ~9,000
   characters of retrieved context, matching `_CHAT_TOP_K=5` chunks at up to
   1,800 chars each) took `73s` measured directly against Ollama's API,
   bypassing this app's HTTP layer entirely — confirming the *model
   inference itself*, not the app, was the slow part.
3. Bumped `OLLAMA_TIMEOUT_SECONDS` to 120 and re-ran real requests through
   the actual `/api/chat`, `/api/essay`, and `/api/artifact` endpoints (not
   mocks) on this CPU-only machine:
   - `/api/chat`: succeeded, `64s`.
   - `/api/essay`: succeeded on retry at `78s` and `105s` across two runs
     (one earlier attempt also hit a race with the Supabase pooled
     connection closing during an unusually slow generation — a separate,
     narrower issue from the timeout itself).
   - `/api/artifact`: **failed** at `121s` — just over the 120s ceiling. The
     HTML artifact skill's system prompt (full document structure rules) and
     expected output (a complete HTML document) are the largest of the three
     generation paths, so it was consistently the slowest.

## Fix

Raised `OLLAMA_TIMEOUT_SECONDS` to 180, with the reasoning and the actual
measured numbers written directly into `app/config.py`'s comment and
`.env.example`, not just "increased the timeout" with no context for why 180
specifically. Left it configurable via env var since real hardware varies
far more than any one number can account for.

## Lesson

"The timeout was too short" is not a hypothesis to fix from theory — it's a
number to measure. Testing the mocked unit-test path (which stubs out
`generate_with_fallback` entirely) would never have caught this at all,
because the mock returns instantly; only running the real system end-to-end,
with the real local model, under real CPU constraints, surfaced it. Given
this project's explicit "local Ollama demo is mandatory" requirement, this
is exactly the kind of failure that would have shown up silently during an
evaluator's actual demo run if it had only been unit-tested.
