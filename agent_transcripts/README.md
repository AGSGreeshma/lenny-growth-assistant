# Agent Transcripts

This directory contains development and debugging records produced while building the Lenny Growth Assistant.

The transcripts document problems encountered during development, the investigation performed, the corrections applied, and the resulting lessons.

## Included Debugging Records

- `01-cors-debugging.md` — Frontend/backend CORS issue and resolution
- `02-backend-api-debugging.md` — PowerShell request formatting and `/ask` validation errors
- `03-frontend-backend-connection.md` — Frontend API connection and CORS troubleshooting
- `04-agent-sdk-routing-only-decision.md` — Why the Claude Agent SDK classifies intent but never writes the final answer, and how the two mandatory-but-conflicting requirements (Agent SDK + local-only demo) were reconciled
- `05-router-mock-patching-bug.md` — A "patch where it's used, not where it's defined" mocking bug found while writing the LLM fallback tests
- `06-rag-grounding-structural-fix.md` — Replacing prompt-based "say you don't know" grounding with a structural similarity floor + no-LLM-call short circuit
- `07-corrupted-venv-dll-debugging.md` — Diagnosing and fixing a corrupted Windows venv (numpy/torch/scipy "DLL load failed" errors) blocking the test suite
- `08-provider-toggle-scope-decision.md` — Scoping the frontend provider-toggle UI into an actual per-request backend override, not a cosmetic-only control
- `09-ollama-timeout-tuning-from-live-measurement.md` — Discovering and fixing a too-short Ollama timeout by measuring real request durations end-to-end (a bug mocked unit tests could never have caught)
- `10-turn-aware-chunking-regex-bug.md` — A regex using `\s*` instead of `[ \t]*` silently swallowed a whole paragraph as a "speaker name" by matching across a line boundary, caught by a value-level (not just count-level) smoke test
- `11-hedging-answer-prompt-fix.md` — Diagnosing and fixing answers that correctly cited sources yet still claimed "the transcripts don't provide enough information" — a system-prompt instruction that was redundant with (and fighting against) the retrieval floor added later
- `12-accessibility-audit-pass.md` — A full component-by-component accessibility pass found the app had no `<h1>` once a conversation started, and five interactive controls missing the focus-visible style used everywhere else

## Purpose

These records demonstrate the iterative development and debugging process used while building the application.

No API keys, passwords, tokens, or other secrets should be stored in these transcripts.
