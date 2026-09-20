import os

from dotenv import load_dotenv

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Gemini is the AUTO-chain cloud fallback (Ollama -> Gemini); OpenAI remains
# fully wired but reachable only via explicit provider="openai" /
# FORCE_LLM_PROVIDER=openai, never automatically -- see app/llm/router.py.
# Uses Gemini's OpenAI-compatible endpoint (GEMINI_BASE_URL below) through
# the same `openai` pip package OpenAIClient already uses, not a separate
# Google SDK -- see app/llm/gemini_client.py.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# gemini-2.0-flash is deprecated/shut down (confirmed against ai.google.dev
# docs, not assumed) -- do not revert to it. gemini-2.5-flash is the
# default: free-tier eligible with a documented quota (1,500 requests/day,
# 1M TPM as of this writing) and an established track record. Configurable
# specifically because Gemini's model lineup moves fast -- check
# https://ai.google.dev/gemini-api/docs/models and your own AI Studio
# dashboard before assuming this value is still current.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
# ENGINEERING DECISION (not an accidental limitation): this is a SOFT
# wall-clock generation budget, not a hard request timeout. app/llm/router.py
# and app/llm/ollama_client.py stream the response token-by-token and, if
# this budget is spent before the model finishes, return whatever coherent
# content has been generated so far (trimmed to a clean sentence boundary)
# rather than discarding it. A locally-generated response -- especially the
# Ship 30 for 30 essay, whose IDEAL target is ~1,250 words -- may therefore
# come back shorter than that target on CPU-only hardware. This is
# intentional: within this budget, a complete, coherent, grounded response
# takes priority over forcing an exact word count. See app/skills/ship30.py
# for how the prompt reflects this same priority order.
#
# Chosen deliberately at 120s for a reproducible local demo, even though
# earlier live measurement on this project's own reference hardware showed
# full-length generation taking meaningfully longer (Ship 30 essay ~193-273s,
# HTML artifact ~121-198s, depending on target length and CPU-only
# throughput -- see agent_transcripts/09 and agent_transcripts/13 for the
# actual measurements this number is based on). On slower hardware, expect
# more requests to return a shorter-than-ideal response, or -- once the
# response is too short to be useful at all -- an actionable timeout error,
# rather than the ideal ~1,250-word essay every time. A configured
# OPENAI_API_KEY (see below) gives the same request a much larger
# effective headroom without raising this value, since cloud inference isn't
# bound by this machine's CPU throughput. This value must also be forwarded
# through docker-compose.yml's backend environment block, not just set here
# -- it was previously missing there, which meant Docker deployments
# silently ignored whatever was configured and always used a hardcoded
# fallback.
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
FORCE_LLM_PROVIDER = os.getenv("FORCE_LLM_PROVIDER", "").strip().lower() or None

# Ollama's per-model default context window (4096 for llama3.2:3b) has to
# hold BOTH the retrieved transcript context (up to 6 chunks x 2500 chars for
# the Ship 30 essay -- see app/skills/ship30.py) AND the generated output.
# With no explicit options, the essay was observed truncating around ~650
# words instead of the assignment's ~1,250-word target, because there wasn't
# enough context budget left for the full output. num_ctx gives headroom for
# input+output together; num_predict caps how many tokens the model is
# allowed to generate (comfortably above the ~1,670 tokens a 1,250-word essay
# needs, with room for the longer HTML-artifact skill too). Raising these
# increases generation time for the *longer* output specifically -- that's
# unavoidable, not a regression -- so re-measure OLLAMA_TIMEOUT_SECONDS after
# changing them.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "3000"))

# Cosine-similarity floor for the retriever (app/rag/retriever.py). Chunks
# scoring below this are treated as noise, not evidence -- this is what lets
# the assistant say "I don't know" structurally for out-of-domain questions.
# Tune down if genuinely relevant answers are being rejected too often; tune
# up if clearly irrelevant chunks are still reaching the LLM.
RAG_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.30"))

# The agent layer (app/agent/orchestrator.py) routes chat messages through
# the Claude Agent SDK by default, and falls back to a local keyword router
# if the SDK/CLI/network is unavailable. Setting this to "false" skips the
# SDK attempt entirely -- useful for a fully offline/Ollama-only demo where
# you don't want the app to spend time (or make an outbound call) trying the
# cloud-based router before falling back.
AGENT_SDK_ENABLED = os.getenv("AGENT_SDK_ENABLED", "true").strip().lower() != "false"
