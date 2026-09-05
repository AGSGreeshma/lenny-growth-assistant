"""
Shared dual-provider routing: try Ollama first (satisfies the "local model
required for the demo" requirement), fall back to OpenAI on any failure
(timeout, connection error, etc.) so a flaky local setup never blocks a
request. Used by both the grounded-answer generator and the Ship 30 skill,
so the fallback logic lives in exactly one place.
"""

import logging

from app.config import OLLAMA_BASE_URL, OPENAI_API_KEY
from app.llm.ollama_client import OllamaClient
from app.llm.openai_client import OpenAIClient

logger = logging.getLogger("lenny-assistant")

OLLAMA_MODEL = "llama3.2:3b"


async def generate_with_fallback(
    messages: list[dict[str, str]],
    system_prompt: str,
) -> str:
    ollama = OllamaClient(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL)

    try:
        return await ollama.generate(messages=messages, system_prompt=system_prompt)
    except Exception as exc:
        logger.warning("Ollama failed (%s) -- falling back to OpenAI", exc)

    if not OPENAI_API_KEY:
        raise RuntimeError("Ollama failed and OPENAI_API_KEY is not configured.")

    try:
        openai_client = OpenAIClient()
        return await openai_client.generate(messages=messages, system_prompt=system_prompt)
    except Exception as exc:
        raise RuntimeError(f"Both Ollama and OpenAI generation failed: {exc}") from exc