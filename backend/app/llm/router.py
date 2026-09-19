import logging

import httpx

from app.config import (
    FORCE_LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_PREDICT,
    OLLAMA_TIMEOUT_SECONDS,
    OPENAI_API_KEY,
)
from app.llm.ollama_client import OllamaClient

logger = logging.getLogger("lenny-assistant")

# Below this many words, a soft-deadline cutoff (see OllamaClient.generate)
# produced too little to be a useful response -- e.g. generation was still
# mid-Hook when the budget ran out. Below this threshold we treat it the
# same as an outright failure so a cloud fallback (if configured) gets a
# chance, instead of returning a near-empty fragment as if it were a real
# answer.
_MIN_USEFUL_WORDS = 60


class GenerationTimeoutError(RuntimeError):
    """Raised when local generation could not produce a useful response
    within OLLAMA_TIMEOUT_SECONDS and no cloud fallback is available (or the
    caller explicitly forced the ollama provider). Callers (the API layer)
    catch this separately from a generic RuntimeError so they can return a
    clean, specific, actionable message instead of a generic 502."""


def _timeout_message() -> str:
    return (
        f"Local generation exceeded the {OLLAMA_TIMEOUT_SECONDS:.0f}-second runtime "
        "limit. Please try again with a shorter request, or configure a supported "
        "cloud provider (OPENAI_API_KEY) for faster long-form generation."
    )


async def _generate_via_openai(messages: list[dict[str, str]], system_prompt: str) -> str:
    from app.llm.openai_client import OpenAIClient

    openai_client = OpenAIClient()
    return await openai_client.generate(messages=messages, system_prompt=system_prompt)


async def _fallback_to_openai(
    messages: list[dict[str, str]], system_prompt: str, cause: Exception
) -> tuple[str, str]:
    """Shared by both fallback entry points: an outright Ollama exception,
    and an Ollama soft-deadline cutoff that produced too little content to
    be useful. `cause` is preserved for chaining and re-raised as-is when no
    cloud provider is configured, so a timeout stays a timeout message
    rather than becoming a generic "not configured" message."""
    if not OPENAI_API_KEY:
        if isinstance(cause, GenerationTimeoutError):
            raise cause
        raise RuntimeError("Ollama failed and OPENAI_API_KEY is not configured.") from cause

    try:
        answer = await _generate_via_openai(messages, system_prompt)
        return answer, "openai"
    except Exception as exc:
        raise RuntimeError(f"Both Ollama and OpenAI generation failed: {exc}") from exc


async def generate_with_fallback(
    messages: list[dict[str, str]],
    system_prompt: str,
    force_provider: str | None = None,
) -> tuple[str, str]:
    """Returns (answer, provider) where provider is "ollama" or "openai".

    `force_provider` is a per-request override (from the frontend's provider
    toggle) that takes precedence over the FORCE_LLM_PROVIDER env var, which
    remains the deployment-wide default when no request specifies one.

    OLLAMA_TIMEOUT_SECONDS is a soft wall-clock budget, not a hard cutoff:
    OllamaClient streams the response and returns whatever was generated so
    far once the budget runs out (see app/llm/ollama_client.py). A response
    that's merely shorter than the ideal target because of that budget is
    still returned as a normal success; only a cutoff that produced too
    little to be useful (see _MIN_USEFUL_WORDS) is treated as a failure.
    """
    effective_force = force_provider or FORCE_LLM_PROVIDER

    if effective_force == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OpenAI provider was requested but OPENAI_API_KEY is not configured."
            )
        answer = await _generate_via_openai(messages, system_prompt)
        return answer, "openai"

    ollama = OllamaClient(
        base_url=OLLAMA_BASE_URL,
        model=OLLAMA_MODEL,
        timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
        num_ctx=OLLAMA_NUM_CTX,
        num_predict=OLLAMA_NUM_PREDICT,
    )

    try:
        answer, hit_deadline = await ollama.generate(messages=messages, system_prompt=system_prompt)
    except Exception as exc:
        if effective_force == "ollama":
            # Ollama was explicitly requested -- do not silently fall back to
            # a different provider than the one the caller asked for.
            if isinstance(exc, httpx.TimeoutException):
                raise GenerationTimeoutError(_timeout_message()) from exc
            raise RuntimeError(f"Ollama was requested but generation failed: {exc}") from exc
        logger.warning("Ollama failed (%s) -- falling back to OpenAI", exc)
        return await _fallback_to_openai(messages, system_prompt, cause=exc)

    if hit_deadline and len(answer.split()) < _MIN_USEFUL_WORDS:
        cause = GenerationTimeoutError(_timeout_message())
        if effective_force == "ollama":
            raise cause
        logger.warning(
            "Ollama hit the %.0fs soft deadline with too little output (%d words) -- "
            "falling back to OpenAI", OLLAMA_TIMEOUT_SECONDS, len(answer.split()),
        )
        return await _fallback_to_openai(messages, system_prompt, cause=cause)

    if hit_deadline:
        logger.warning(
            "Ollama generation hit the %.0fs soft deadline -- returning a shorter, "
            "trimmed response (%d words) rather than continuing past the runtime budget.",
            OLLAMA_TIMEOUT_SECONDS, len(answer.split()),
        )

    return answer, "ollama"
