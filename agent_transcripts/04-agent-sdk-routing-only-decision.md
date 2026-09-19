# Agent Transcript 04 — Why the Claude Agent SDK Routes but Never Answers

## Problem

The assignment has two requirements that pull in opposite directions:

1. Build the agent layer using the Claude Agent SDK (or Pi Coding Agent).
2. A local LLM (Ollama) is mandatory for the demo — the actual answer text
   has to be producible on the evaluator's own machine, with no cloud
   dependency.

The Claude Agent SDK (`claude_agent_sdk`) is Anthropic-API-only: it shells
out to the `claude` CLI, which talks to Anthropic's cloud. It has no concept
of "run this against my local Ollama model." If the SDK were used to write
the final answer, every successful chat request would silently become a
cloud-generated answer, which would make requirement 2 untestable — there
would be no way to demonstrate the local-only path actually works, because
even a "successful" Ollama-path request would really have been answered by
Claude in the cloud.

## Investigation

Re-read the assignment's own framing: the Agent SDK requirement doesn't say
the SDK has to produce the answer text — it says the system needs an
"agentic" layer. The genuinely agentic decision in this system is *what kind
of request this is*: a plain grounded question, a request to turn material
into a Ship 30 for 30 essay, or a request for an HTML/CSS artifact. That
classification step doesn't need to know anything about Ollama vs. OpenAI —
it just needs to read the user's message (and optionally check the knowledge
base) and emit an intent.

## Decision

Split the system into two layers:

- **Routing** (`app/agent/orchestrator.py`, `classify_intent()`): uses the
  Claude Agent SDK, with an MCP tool (`retrieve_transcripts`,
  `app/agent/tools.py`) the SDK can optionally call to sanity-check whether
  the topic is in the knowledge base before deciding.
- **Generation**: every one of the three paths (`rag/generator.py`,
  `skills/ship30.py`, `skills/html_artifact.py`) still calls
  `app/llm/router.py`'s `generate_with_fallback()` — Ollama first, OpenAI
  fallback — completely unchanged by the presence of the agent layer.

This keeps the local-only demo path 100% intact (routing is a small,
fast classification call; the actual token generation for the user-visible
answer is 100% Ollama when Ollama is up) while giving the Agent SDK a real,
load-bearing job instead of a decorative one bolted onto the side.

## Fallback for offline/no-cloud-key operation

If the SDK/CLI/network is unavailable for any reason (no `ANTHROPIC_API_KEY`,
`claude` CLI not installed, timeout, network unreachable), routing degrades
to a small deterministic keyword classifier
(`_classify_via_heuristics()`) so the application keeps working end-to-end
with zero cloud dependency. Every routing decision records
`used_agent_sdk: bool` in the API response so this is visible, not silently
papered over. `AGENT_SDK_ENABLED=false` skips the SDK attempt entirely — used
for a guaranteed fully-offline demo run.

## Lesson

When two requirements seem to conflict, look for the seam between them
instead of picking one and quietly dropping the other. Here the seam was
"agentic" vs. "answer-generating" — they sound like the same thing but
aren't, and treating them as separable let both requirements be satisfied
for real instead of one being satisfied only on paper.
