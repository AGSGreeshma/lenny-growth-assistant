# Agent Transcript 08 — Scoping the Provider-Toggle UI

## Problem

The remaining-work list called for a "provider-toggle UI control" without
specifying its mechanics. The existing provider-selection mechanism
(`FORCE_LLM_PROVIDER` env var, read once in `app/config.py` at process
startup) is deployment-wide and requires restarting the backend to change —
that's not a "toggle" a user can operate from the UI at all.

## Options considered

1. **Display-only indicator**: show which provider *was* used for the last
   response (already existed — `ChatResponse.provider`, rendered as a badge
   in `ChatMessage.jsx`/`ArtifactViewer.jsx`) but give the user no actual
   control. Minimal work, but doesn't satisfy "toggle."
2. **Client-side-only preference that silently does nothing**: add a toggle
   in the UI that isn't actually wired to any backend behavior. Rejected
   immediately — a control that doesn't control anything is worse than no
   control, because it actively misleads the user about what the app is
   doing.
3. **Real per-request override**: add an optional `provider` field to
   `ChatRequest`/`EssayRequest`/`ArtifactRequest`, thread it through
   `generate_answer()` / `generate_ship30_essay()` / `generate_html_artifact()`
   down to `generate_with_fallback()`, and let the frontend send the current
   toggle state with every request.

## Decision

Went with option 3. `generate_with_fallback()` gained a `force_provider`
parameter that takes precedence over the `FORCE_LLM_PROVIDER` env var for
that one call (the env var remains the deployment-wide default when no
request specifies an override). Explicitly requesting `"ollama"` was made to
fail loudly if Ollama fails, rather than silently falling back to OpenAI —
if the user specifically asked to test/use the local path, silently handing
them a cloud answer instead would defeat the point of the toggle and could
mask a real local-model problem during a demo.

The frontend toggle (`Header.jsx`'s `ProviderToggle`) has three states: Auto
(no override — the normal Ollama-first/OpenAI-fallback behavior), Ollama
(force local, fail if it fails), and OpenAI (force cloud). The choice
persists in `localStorage` across page reloads but is not synced to the
backend or stored per-session — it's a client preference, not application
state.

## Trade-off

This threads a new parameter through four function signatures
(`generate_with_fallback`, `generate_answer`, `generate_ship30_essay`,
`generate_html_artifact`) purely to carry one optional string. A slightly
"cleaner" alternative would have been a module-level context variable or a
request-scoped dependency-injected setting, but explicit parameter threading
was chosen because it keeps the override visible at every call site and
trivially testable with plain function calls — no hidden global state to
reset between tests. Given the small number of call sites, the extra
verbosity was judged worth the traceability.

## Lesson

"Add a toggle" is an underspecified request until you know what the toggle
actually changes at runtime. Tracing the existing provider-selection
mechanism back to a process-startup-only env var first was necessary before
any UI work could start — building the toggle first and discovering it had
nothing real to control would have been wasted work.
