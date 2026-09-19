import os

from dotenv import load_dotenv

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
# Measured live, end-to-end, against this app's own API on reference
# CPU-only hardware (llama3.2:3b): plain chat ~64s, Ship 30 essay ~78-105s,
# HTML artifact ~121s+ (its system prompt + expected output are the largest
# of the three skills). A 60s timeout reliably failed real requests; even
# 120s intermittently timed out the HTML artifact path specifically.
#
# Re-measured later, on a different machine, after its GPU/CUDA path turned
# out to be broken (a driver-level crash, not a code issue -- see
# docs/architecture.md) and Ollama fell back to CPU-only inference there:
# Ship 30 essay measured 198.6s and HTML artifact 180.5s end-to-end, both
# above the previous 180s value. CPU-only throughput varies meaningfully by
# machine, so 300s was chosen for real headroom above the slowest measurement
# actually observed, not the fastest; tune via this env var for slower/faster
# hardware. This value must also be forwarded through docker-compose.yml's
# backend environment block, not just set here -- it was previously missing
# there, which meant Docker deployments silently ignored whatever was
# configured and always used this hardcoded fallback.
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))
FORCE_LLM_PROVIDER = os.getenv("FORCE_LLM_PROVIDER", "").strip().lower() or None

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
