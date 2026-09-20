import logging

import httpx

from app.config import (
    FORCE_LLM_PROVIDER,
    GEMINI_API_KEY,
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
        "cloud provider (GEMINI_API_KEY) for faster long-form generation."
    )


async def _generate_via_openai(messages: list[dict[str, str]], system_prompt: str) -> str:
    from app.llm.openai_client import OpenAIClient

    openai_client = OpenAIClient()
    return await openai_client.generate(messages=messages, system_prompt=system_prompt)


async def _generate_via_gemini(messages: list[dict[str, str]], system_prompt: str) -> str:
    from app.llm.gemini_client import GeminiClient

    gemini_client = GeminiClient()
    return await gemini_client.generate(messages=messages, system_prompt=system_prompt)


async def _fallback_to_gemini(
    messages: list[dict[str, str]], system_prompt: str, cause: Exception
) -> tuple[str, str]:
    """The AUTO chain's only cloud fallback: Ollama -> Gemini. Shared by both
    fallback entry points below -- an outright Ollama exception, and an
    Ollama soft-deadline cutoff that produced too little content to be
    useful. `cause` is preserved for chaining and re-raised as-is when no
    Gemini key is configured, so a timeout stays a timeout message rather
    than becoming a generic "not configured" message.

    Deliberately does NOT cascade to OpenAI on Gemini failure -- OpenAI is
    reachable only via explicit provider selection (force_provider=
    "openai" / FORCE_LLM_PROVIDER=openai), never as part of the automatic
    chain. This is a product decision (keep OpenAI credits untouched until
    explicitly opted into), not an oversight."""
    if not GEMINI_API_KEY:
        if isinstance(cause, GenerationTimeoutError):
            raise cause
        raise RuntimeError("Ollama failed and GEMINI_API_KEY is not configured.") from cause

    try:
        answer = await _generate_via_gemini(messages, system_prompt)
        return answer, "gemini"
    except Exception as exc:
        raise RuntimeError(f"Both Ollama and Gemini generation failed: {exc}") from exc


async def generate_with_fallback(
    messages: list[dict[str, str]],
    system_prompt: str,
    force_provider: str | None = None,
) -> tuple[str, str]:
    """Returns (answer, provider) where provider is "ollama", "gemini", or
    "openai".

    `force_provider` is a per-request override (from the frontend's provider
    toggle) that takes precedence over the FORCE_LLM_PROVIDER env var, which
    remains the deployment-wide default when no request specifies one.

    AUTO chain (no explicit provider): Ollama -> Gemini only. OpenAI is
    never entered automatically -- it's reachable exclusively via explicit
    provider="openai" / FORCE_LLM_PROVIDER=openai, so a deployment with an
    unfunded or intentionally-reserved OpenAI key is never silently billed
    by the automatic fallback path.

    Explicit provider selection ("ollama" | "gemini" | "openai") never
    falls back to a different provider than the one asked for -- a failure
    there raises, it doesn't silently switch.

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

    if effective_force == "gemini":
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "Gemini provider was requested but GEMINI_API_KEY is not configured."
            )
        answer = await _generate_via_gemini(messages, system_prompt)
        return answer, "gemini"

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
        logger.warning("Ollama failed (%s) -- falling back to Gemini", exc)
        return await _fallback_to_gemini(messages, system_prompt, cause=exc)

    if hit_deadline and len(answer.split()) < _MIN_USEFUL_WORDS:
        cause = GenerationTimeoutError(_timeout_message())
        if effective_force == "ollama":
            raise cause
        logger.warning(
            "Ollama hit the %.0fs soft deadline with too little output (%d words) -- "
            "falling back to Gemini", OLLAMA_TIMEOUT_SECONDS, len(answer.split()),
        )
        return await _fallback_to_gemini(messages, system_prompt, cause=cause)

    if hit_deadline:
        logger.warning(
            "Ollama generation hit the %.0fs soft deadline -- returning a shorter, "
            "trimmed response (%d words) rather than continuing past the runtime budget.",
            OLLAMA_TIMEOUT_SECONDS, len(answer.split()),
        )

    return answer, "ollama"
