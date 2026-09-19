"""
Agent layer: Claude Agent SDK-based routing.

Why routing, not answer-writing
--------------------------------
The assignment requires two things that pull in different directions:

1. "Build the agent layer using the Anthropic Claude Agent SDK or Pi Coding
   Agent" -- the Claude Agent SDK talks to the Anthropic API, so it is
   cloud-only. It has no concept of "run this against my local Ollama
   model."
2. "Local LLM -- mandatory for the demo" -- the actual answer text has to be
   producible by a model running on the evaluator's own machine, with no
   cloud dependency at all.

If the Agent SDK were used to *write the final answer*, every successful
request would silently become a cloud-generated answer, which would make the
"local model" requirement untestable in practice. Instead, this module uses
the Agent SDK for exactly the piece of the system that is genuinely
agentic -- deciding *what kind of request this is* (a plain grounded
question, a Ship 30 for 30 essay request, or an HTML/CSS artifact request)
and, when useful, checking the knowledge base before deciding. The actual
token generation for every one of those three paths still flows through
``app.llm.router.generate_with_fallback`` (Ollama first, OpenAI fallback),
completely unchanged. This keeps the local-only demo path 100% intact while
giving the Agent SDK a real, load-bearing job: routing.

How the SDK reaches Anthropic
------------------------------
``claude_agent_sdk`` (the pip package in requirements.txt) spawns a local
Claude Code CLI process and talks to it over stdio; that CLI process is what
actually calls the Anthropic API. On the platforms this project ships for
(Windows and Linux, confirmed by inspecting both installs), **the CLI binary
is bundled inside the pip package itself** (`claude_agent_sdk/_bundled/`) --
`pip install -r requirements.txt` is sufficient. No separate
`npm install -g @anthropic-ai/claude-code` step, and no `claude` CLI on PATH,
is required. See `.env.example` and `docs/architecture.md` for the full
authentication story (`ANTHROPIC_API_KEY` is the documented, reproducible
path).

permission_mode="dontAsk", not "bypassPermissions"
----------------------------------------------------
This router only ever needs one specific, narrow, read-only tool
(`mcp__lenny__retrieve_transcripts`, granted via `allowed_tools` below) --
it never needs file edits, shell access, or any of the general-purpose
tools Claude Code normally exposes. `permission_mode="dontAsk"` ("don't
prompt for permissions; deny if not pre-approved") lets that one
pre-approved tool run without an interactive prompt (there's no terminal to
prompt in a server process) while denying everything else by default --
least-privilege, and it never sends the CLI's `--dangerously-skip-permissions`
flag. `"bypassPermissions"` was tried first and rejected: it auto-approves
*every* tool call, not just the one this router needs, and the bundled CLI
additionally refuses to honor it when the process is running as root/sudo
(a real, reproducible failure inside a default Docker container, which runs
as root unless told otherwise) -- a second, independent reason to prefer the
narrower mode here rather than switching the container to a non-root user.

Failure handling
----------------
If the Agent SDK is unavailable for any reason (`ANTHROPIC_API_KEY` isn't
configured, no Claude Code login session exists either, the process times
out, the network is unreachable), routing falls back to a small
deterministic keyword classifier so the application keeps working
end-to-end with zero cloud dependency -- which is also exactly what the
mandatory offline/Ollama demo needs. Every routing decision records which
path was used (`used_agent_sdk: bool`) so this is visible in logs, not
silently papered over.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass

from app.agent.tools import build_retrieval_tool
from app.config import AGENT_SDK_ENABLED

logger = logging.getLogger("lenny-assistant.agent")

VALID_INTENTS = {"chat", "essay", "html_artifact"}

ROUTER_SYSTEM_PROMPT = """You are the routing layer for Lenny's Growth Assistant, \
an internal tool that answers product/growth questions from Lenny's Podcast \
transcripts.

You do NOT answer the user's question yourself. Your only job is to classify \
the user's latest message into exactly one of three intents, and to extract \
a clean topic string for it:

- "chat": a normal product/growth/startup question that should be answered \
  from the transcript knowledge base.
- "essay": the user is asking for a Ship 30 for 30-style essay/write-up to be \
  generated (e.g. "turn this into an essay", "write a Ship 30 essay about \
  onboarding", "make this into a Ship 30 post").
- "html_artifact": the user is asking for a rendered HTML/CSS page, landing \
  page, one-pager, or visual summary (e.g. "give me this as an HTML page", \
  "make a one-page HTML summary").

You may call the retrieve_transcripts tool if it would help you judge whether \
the topic is something the knowledge base likely covers, but you are not \
required to.

You may be given recent conversation turns before the latest message, to help \
you resolve references like "this" or "that" in the latest message (e.g. \
"turn this into an essay" after a question about onboarding means the topic \
is onboarding, not the literal phrase "this"). Use that context only to fill \
in the topic -- always base the intent classification itself on the latest \
message.

Respond with ONLY a single JSON object on its own line, no other text, no \
markdown fences:
{"intent": "chat" | "essay" | "html_artifact", "topic": "<the underlying question or topic, in the user's own words>"}
"""

AGENT_SDK_TIMEOUT_SECONDS = 25


@dataclass
class RoutingDecision:
    intent: str
    topic: str
    used_agent_sdk: bool
    router_error: str | None = None


async def classify_intent(
    message: str, db, history: list[dict] | None = None
) -> RoutingDecision:
    """Classify a chat message's intent, preferring the Claude Agent SDK and
    degrading to a heuristic router if the SDK path fails for any reason.

    ``history`` (prior turns of the current session, oldest first) is
    optional context used only to resolve referential phrasing like "turn
    this into an essay" back to the actual topic discussed earlier -- it
    never changes which intent is picked, only what topic string is
    extracted for essay/html_artifact intents."""
    if not AGENT_SDK_ENABLED:
        logger.info("AGENT_SDK_ENABLED=false -- routing via the local heuristic router only")
        return _classify_via_heuristics(message, history)

    try:
        decision = await asyncio.wait_for(
            _classify_via_agent_sdk(message, db, history), timeout=AGENT_SDK_TIMEOUT_SECONDS
        )
        logger.info("Routed via Claude Agent SDK: intent=%s", decision.intent)
        return decision
    except Exception as exc:  # noqa: BLE001 - any SDK/CLI/network failure degrades gracefully
        logger.warning(
            "Claude Agent SDK routing unavailable (%s: %s); falling back to the "
            "heuristic router so the app keeps working offline.",
            type(exc).__name__,
            exc,
        )
        decision = _classify_via_heuristics(message, history)
        decision.router_error = f"{type(exc).__name__}: {exc}"
        return decision


def _format_recent_history(history: list[dict] | None) -> str:
    """Compact rendering of the last few turns, just enough for the router
    to resolve a referential "this"/"that" in the latest message -- not a
    full transcript, so this stays cheap to send on every routing call."""
    if not history:
        return ""
    lines = []
    for turn in history[-4:]:
        role = "User" if turn.get("role") == "user" else "Assistant"
        content = (turn.get("content") or "")[:400]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _last_user_message(history: list[dict] | None) -> str | None:
    if not history:
        return None
    for turn in reversed(history):
        if turn.get("role") == "user":
            return turn.get("content")
    return None


async def _classify_via_agent_sdk(
    message: str, db, history: list[dict] | None = None
) -> RoutingDecision:
    # Imported lazily so a missing/broken claude_agent_sdk installation only
    # breaks routing (caught above), never the whole application at import time.
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

    server = build_retrieval_tool(db)
    options = ClaudeAgentOptions(
        mcp_servers={"lenny": server},
        allowed_tools=["mcp__lenny__retrieve_transcripts"],
        system_prompt=ROUTER_SYSTEM_PROMPT,
        # "dontAsk", not "bypassPermissions" -- see the module docstring.
        # Denies anything not in allowed_tools instead of auto-approving
        # every tool call, and (unlike bypassPermissions) never sends
        # --dangerously-skip-permissions, which the bundled CLI refuses to
        # honor when running as root (the default in a Docker container).
        permission_mode="dontAsk",
        max_turns=3,
    )

    recent = _format_recent_history(history)
    prompt = (
        f"Recent conversation:\n{recent}\n\nLatest message: {message}" if recent else message
    )

    final_text = None
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    final_text = block.text

    if not final_text:
        raise RuntimeError("Claude Agent SDK returned no assistant text")

    data = _extract_json_object(final_text)
    intent = data.get("intent") if isinstance(data, dict) else None
    if intent not in VALID_INTENTS:
        intent = "chat"
    topic = (data.get("topic") if isinstance(data, dict) else None) or message
    return RoutingDecision(intent=intent, topic=topic, used_agent_sdk=True)


def _extract_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in Agent SDK routing output")
    return json.loads(match.group(0))


_ESSAY_KEYWORDS = (
    "ship 30",
    "ship30",
    "turn this into an essay",
    "turn that into an essay",
    "write an essay",
    "write a ship 30",
    "essay about",
    "essay on",
)
_HTML_KEYWORDS = (
    "html page",
    "html artifact",
    "as html",
    "as an html",
    "web page",
    "webpage",
    "landing page",
    "one-pager",
    "one pager",
    "html/css",
    "html and css",
)


def _looks_referential(message: str) -> bool:
    """True for phrasing like "turn this into an essay" or "give me this as
    HTML" -- a pronoun standing in for a topic from earlier in the
    conversation, with no topic of its own (as opposed to e.g. "write a ship
    30 post about onboarding", which already names its own subject)."""
    words = set(re.findall(r"[a-z']+", message.lower()))
    has_pronoun = bool(words & {"this", "that"})
    has_own_subject = bool(words & {"about", "on"})
    return has_pronoun and not has_own_subject


def _classify_via_heuristics(message: str, history: list[dict] | None = None) -> RoutingDecision:
    lowered = message.lower()
    if any(kw in lowered for kw in _ESSAY_KEYWORDS):
        intent = "essay"
    elif any(kw in lowered for kw in _HTML_KEYWORDS):
        intent = "html_artifact"
    else:
        return RoutingDecision(intent="chat", topic=message, used_agent_sdk=False)

    topic = message
    if _looks_referential(message):
        prior_topic = _last_user_message(history)
        if prior_topic:
            topic = prior_topic

    return RoutingDecision(intent=intent, topic=topic, used_agent_sdk=False)
