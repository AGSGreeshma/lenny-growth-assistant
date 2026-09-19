import logging

from app.config import (
    FORCE_LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    OPENAI_API_KEY,
)
from app.llm.ollama_client import OllamaClient

logger = logging.getLogger("lenny-assistant")


async def generate_with_fallback(
    messages: list[dict[str, str]],
    system_prompt: str,
    force_provider: str | None = None,
) -> tuple[str, str]:
    """Returns (answer, provider) where provider is "ollama" or "openai".

    `force_provider` is a per-request override (from the frontend's provider
    toggle) that takes precedence over the FORCE_LLM_PROVIDER env var, which
    remains the deployment-wide default when no request specifies one.
    """
    effective_force = force_provider or FORCE_LLM_PROVIDER

    if effective_force == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OpenAI provider was requested but OPENAI_API_KEY is not configured."
            )
        from app.llm.openai_client import OpenAIClient

        openai_client = OpenAIClient()
        answer = await openai_client.generate(messages=messages, system_prompt=system_prompt)
        return answer, "openai"

    ollama = OllamaClient(
        base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, timeout_seconds=OLLAMA_TIMEOUT_SECONDS
    )

    try:
        answer = await ollama.generate(messages=messages, system_prompt=system_prompt)
        return answer, "ollama"
    except Exception as exc:
        if effective_force == "ollama":
            # Ollama was explicitly requested -- do not silently fall back to
            # a different provider than the one the caller asked for.
            raise RuntimeError(f"Ollama was requested but generation failed: {exc}") from exc
        logger.warning("Ollama failed (%s) -- falling back to OpenAI", exc)

    if not OPENAI_API_KEY:
        raise RuntimeError("Ollama failed and OPENAI_API_KEY is not configured.")

    try:
        from app.llm.openai_client import OpenAIClient

        openai_client = OpenAIClient()
        answer = await openai_client.generate(messages=messages, system_prompt=system_prompt)
        return answer, "openai"
    except Exception as exc:
        raise RuntimeError(f"Both Ollama and OpenAI generation failed: {exc}") from exc