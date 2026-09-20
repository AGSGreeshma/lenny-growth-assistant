"""
LLM provider fallback (app/llm/router.py): Ollama first, Gemini second,
clear failure when neither works. No real network calls -- all three
clients are mocked. This is the behavior the "mandatory local Ollama" and
"cloud LLM" requirements both depend on, and the one place both the plain
chat path and every skill (Ship 30, HTML artifact) share.

OpenAI is deliberately NOT part of the automatic (AUTO) chain -- it's
reachable only via an explicit provider="openai" / FORCE_LLM_PROVIDER=openai
request, so an unfunded or intentionally-reserved OpenAI key is never
silently used by a Gemini/Ollama failure. Tests below cover both the AUTO
chain (Ollama -> Gemini) and each of the three explicit-provider paths
separately.

OllamaClient.generate() returns (content, hit_deadline) -- hit_deadline is
True when the soft OLLAMA_TIMEOUT_SECONDS budget ran out before the model
finished (see app/llm/ollama_client.py). Every mock below returns that same
2-tuple shape to match the real contract.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

import app.llm.router as router_mod
from app.llm.router import GenerationTimeoutError


@pytest.mark.asyncio
async def test_ollama_success_returns_ollama_provider():
    with patch.object(router_mod, "OllamaClient") as MockOllama:
        MockOllama.return_value.generate = AsyncMock(return_value=("hello from ollama", False))
        answer, provider = await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}], system_prompt="sys"
        )
    assert provider == "ollama"
    assert answer == "hello from ollama"


@pytest.mark.asyncio
async def test_ollama_client_constructed_with_configured_timeout():
    """A real 5-chunk RAG prompt measured ~73s on CPU-only reference
    hardware -- if this regresses back to a too-tight timeout, real chat
    requests fail on the mandatory local-only path. Lock in that
    OLLAMA_TIMEOUT_SECONDS is actually threaded through to the client."""
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "OLLAMA_TIMEOUT_SECONDS", 120.0
    ):
        MockOllama.return_value.generate = AsyncMock(return_value=("hello from ollama", False))
        await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}], system_prompt="sys"
        )
    MockOllama.assert_called_once_with(
        base_url=router_mod.OLLAMA_BASE_URL,
        model=router_mod.OLLAMA_MODEL,
        timeout_seconds=120.0,
        num_ctx=router_mod.OLLAMA_NUM_CTX,
        num_predict=router_mod.OLLAMA_NUM_PREDICT,
    )


def test_default_ollama_timeout_is_120_seconds():
    """Locks in the engineering decision documented in app/config.py: 120s
    is the deliberate soft generation budget for the local demo path, not
    the earlier 180s/300s values from before the streaming soft-deadline
    was implemented."""
    assert router_mod.OLLAMA_TIMEOUT_SECONDS == 120.0


# --- AUTO chain: Ollama -> Gemini (OpenAI never entered automatically) -----


@pytest.mark.asyncio
async def test_ollama_failure_falls_back_to_gemini():
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "GEMINI_API_KEY", "AIza-test"
    ), patch("app.llm.gemini_client.GeminiClient") as MockGemini:
        MockOllama.return_value.generate = AsyncMock(side_effect=RuntimeError("connection refused"))
        MockGemini.return_value.generate = AsyncMock(return_value="hello from gemini")

        answer, provider = await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}], system_prompt="sys"
        )

    assert provider == "gemini"
    assert answer == "hello from gemini"


@pytest.mark.asyncio
async def test_auto_chain_never_reaches_openai_on_ollama_failure():
    """The core architectural change under test: AUTO falls back to Gemini
    only. OpenAI must never be constructed/called by the automatic chain,
    even when a valid OPENAI_API_KEY happens to be configured."""
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "GEMINI_API_KEY", "AIza-test"
    ), patch.object(router_mod, "OPENAI_API_KEY", "sk-test"), patch(
        "app.llm.gemini_client.GeminiClient"
    ) as MockGemini, patch(
        "app.llm.openai_client.OpenAIClient"
    ) as MockOpenAI:
        MockOllama.return_value.generate = AsyncMock(side_effect=RuntimeError("connection refused"))
        MockGemini.return_value.generate = AsyncMock(return_value="hello from gemini")

        answer, provider = await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}], system_prompt="sys"
        )

    assert provider == "gemini"
    MockOpenAI.assert_not_called()


@pytest.mark.asyncio
async def test_both_ollama_and_gemini_failing_raises_runtime_error():
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "GEMINI_API_KEY", "AIza-test"
    ), patch("app.llm.gemini_client.GeminiClient") as MockGemini:
        MockOllama.return_value.generate = AsyncMock(side_effect=RuntimeError("ollama down"))
        MockGemini.return_value.generate = AsyncMock(side_effect=RuntimeError("gemini down"))

        with pytest.raises(RuntimeError, match="Both Ollama and Gemini"):
            await router_mod.generate_with_fallback(messages=[], system_prompt="sys")


@pytest.mark.asyncio
async def test_ollama_failure_with_no_gemini_key_configured_raises_clear_error():
    """This is the mandatory Ollama-only demo path: no GEMINI_API_KEY at
    all. A failure here must be an explicit, actionable RuntimeError -- not
    a silent success, not a fall-through to OpenAI, and not an unrelated
    exception."""
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "GEMINI_API_KEY", None
    ):
        MockOllama.return_value.generate = AsyncMock(side_effect=RuntimeError("ollama down"))

        with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not configured"):
            await router_mod.generate_with_fallback(messages=[], system_prompt="sys")


# --- Explicit provider selection: never silently switches -----------------


@pytest.mark.asyncio
async def test_explicit_gemini_provider():
    with patch.object(router_mod, "GEMINI_API_KEY", "AIza-test"), patch(
        "app.llm.gemini_client.GeminiClient"
    ) as MockGemini, patch.object(router_mod, "OllamaClient") as MockOllama:
        MockGemini.return_value.generate = AsyncMock(return_value="explicit gemini answer")

        answer, provider = await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="sys",
            force_provider="gemini",
        )

    assert provider == "gemini"
    assert answer == "explicit gemini answer"
    MockOllama.return_value.generate.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_gemini_with_missing_key_raises_clear_error():
    with patch.object(router_mod, "GEMINI_API_KEY", None):
        with pytest.raises(RuntimeError, match="Gemini provider was requested but GEMINI_API_KEY"):
            await router_mod.generate_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="sys",
                force_provider="gemini",
            )


@pytest.mark.asyncio
async def test_explicit_gemini_failure_does_not_fall_back_to_ollama_or_openai():
    """Explicitly requesting Gemini must fail loudly if Gemini fails, not
    silently hand the answer to a different provider than the one asked
    for -- same contract explicit Ollama already has."""
    with patch.object(router_mod, "GEMINI_API_KEY", "AIza-test"), patch(
        "app.llm.gemini_client.GeminiClient"
    ) as MockGemini, patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "OPENAI_API_KEY", "sk-test"
    ), patch("app.llm.openai_client.OpenAIClient") as MockOpenAI:
        MockGemini.return_value.generate = AsyncMock(
            side_effect=RuntimeError("invalid model: gemini-does-not-exist")
        )

        with pytest.raises(RuntimeError, match="invalid model"):
            await router_mod.generate_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="sys",
                force_provider="gemini",
            )

    MockOllama.return_value.generate.assert_not_called()
    MockOpenAI.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_ollama_provider_unaffected_by_gemini_migration():
    with patch.object(router_mod, "OllamaClient") as MockOllama:
        MockOllama.return_value.generate = AsyncMock(return_value=("explicit ollama answer", False))

        answer, provider = await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="sys",
            force_provider="ollama",
        )

    assert provider == "ollama"
    assert answer == "explicit ollama answer"


@pytest.mark.asyncio
async def test_request_level_force_provider_ollama_does_not_fall_back_to_gemini():
    """Explicitly requesting Ollama must fail loudly if Ollama fails, not
    silently hand the answer to Gemini -- Gemini is the AUTO chain's
    fallback, not a substitute for an explicit choice."""
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "GEMINI_API_KEY", "AIza-test"
    ), patch("app.llm.gemini_client.GeminiClient") as MockGemini:
        MockOllama.return_value.generate = AsyncMock(side_effect=RuntimeError("ollama down"))
        MockGemini.return_value.generate = AsyncMock(return_value="should not be used")

        with pytest.raises(RuntimeError, match="Ollama was requested"):
            await router_mod.generate_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="sys",
                force_provider="ollama",
            )

    MockGemini.return_value.generate.assert_not_called()


@pytest.mark.asyncio
async def test_force_llm_provider_openai_skips_ollama_entirely():
    with patch.object(router_mod, "FORCE_LLM_PROVIDER", "openai"), patch.object(
        router_mod, "OPENAI_API_KEY", "sk-test"
    ), patch("app.llm.openai_client.OpenAIClient") as MockOpenAI, patch.object(
        router_mod, "OllamaClient"
    ) as MockOllama:
        MockOpenAI.return_value.generate = AsyncMock(return_value="forced openai answer")

        answer, provider = await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}], system_prompt="sys"
        )

    assert provider == "openai"
    assert answer == "forced openai answer"
    MockOllama.return_value.generate.assert_not_called()


@pytest.mark.asyncio
async def test_request_level_force_provider_overrides_env_default():
    """The frontend's per-request provider toggle (ChatRequest.provider etc.)
    must take precedence over the FORCE_LLM_PROVIDER env var, not just
    duplicate it."""
    with patch.object(router_mod, "FORCE_LLM_PROVIDER", None), patch.object(
        router_mod, "OPENAI_API_KEY", "sk-test"
    ), patch("app.llm.openai_client.OpenAIClient") as MockOpenAI, patch.object(
        router_mod, "OllamaClient"
    ) as MockOllama:
        MockOpenAI.return_value.generate = AsyncMock(return_value="explicit openai answer")

        answer, provider = await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="sys",
            force_provider="openai",
        )

    assert provider == "openai"
    assert answer == "explicit openai answer"
    MockOllama.return_value.generate.assert_not_called()


@pytest.mark.asyncio
async def test_request_level_force_provider_ollama_does_not_fall_back_to_openai():
    """Explicitly requesting Ollama must fail loudly if Ollama fails, not
    silently hand the answer to a different provider than the one asked
    for."""
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "OPENAI_API_KEY", "sk-test"
    ), patch("app.llm.openai_client.OpenAIClient") as MockOpenAI:
        MockOllama.return_value.generate = AsyncMock(side_effect=RuntimeError("ollama down"))
        MockOpenAI.return_value.generate = AsyncMock(return_value="should not be used")

        with pytest.raises(RuntimeError, match="Ollama was requested"):
            await router_mod.generate_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="sys",
                force_provider="ollama",
            )

    MockOpenAI.return_value.generate.assert_not_called()


# --- Soft-deadline (120s) behavior -----------------------------------------
#
# ENGINEERING DECISION under test: OLLAMA_TIMEOUT_SECONDS is a soft
# wall-clock budget, not a hard cutoff. OllamaClient.generate() streams and
# returns (content, hit_deadline=True) with whatever was generated so far
# when the budget runs out. A *shorter but substantial* response is a normal
# success; a cutoff that produced too little to be useful is treated as a
# failure so a cloud fallback (Gemini, if configured) gets a chance instead
# of returning a near-empty fragment as a real answer.


@pytest.mark.asyncio
async def test_soft_deadline_with_substantial_content_returns_normally():
    """A locally-generated Ship 30 essay that's shorter than the ~1,250-word
    ideal because the 120s budget ran out is not a failure -- it's the
    documented trade-off. Enough words above _MIN_USEFUL_WORDS must be
    returned as a normal, successful 'ollama' response."""
    substantial = " ".join(["word"] * 400) + "."
    with patch.object(router_mod, "OllamaClient") as MockOllama:
        MockOllama.return_value.generate = AsyncMock(return_value=(substantial, True))
        answer, provider = await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}], system_prompt="sys"
        )
    assert provider == "ollama"
    assert answer == substantial


@pytest.mark.asyncio
async def test_soft_deadline_with_too_little_content_falls_back_to_gemini():
    """If the 120s budget runs out while the model is still mid-Hook, the
    fragment isn't useful -- this must behave like a failure and fall back
    to Gemini when configured, not return the fragment as a real answer."""
    tiny_fragment = "In a shocking turn of events, growth teams"
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "GEMINI_API_KEY", "AIza-test"
    ), patch("app.llm.gemini_client.GeminiClient") as MockGemini:
        MockOllama.return_value.generate = AsyncMock(return_value=(tiny_fragment, True))
        MockGemini.return_value.generate = AsyncMock(return_value="hello from gemini")

        answer, provider = await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}], system_prompt="sys"
        )

    assert provider == "gemini"
    assert answer == "hello from gemini"


@pytest.mark.asyncio
async def test_soft_deadline_with_too_little_content_and_no_fallback_raises_timeout_error():
    """The mandatory Ollama-only demo path: no cloud key configured. A
    too-short soft-deadline cutoff must raise the specific
    GenerationTimeoutError (not a generic RuntimeError), so the API layer
    can return the clean, actionable 120-second-limit message instead of a
    generic 502."""
    tiny_fragment = "Just getting started here"
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "GEMINI_API_KEY", None
    ):
        MockOllama.return_value.generate = AsyncMock(return_value=(tiny_fragment, True))

        with pytest.raises(GenerationTimeoutError, match="120-second"):
            await router_mod.generate_with_fallback(
                messages=[{"role": "user", "content": "hi"}], system_prompt="sys"
            )


@pytest.mark.asyncio
async def test_ollama_read_timeout_with_force_provider_ollama_raises_generation_timeout_error():
    """A real httpx timeout (the connection genuinely hanging, or the
    last-resort backstop firing) with the provider explicitly forced to
    ollama must surface as GenerationTimeoutError with the actionable
    message, not a generic RuntimeError wrapping a raw httpx exception
    string."""
    with patch.object(router_mod, "OllamaClient") as MockOllama:
        MockOllama.return_value.generate = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))

        with pytest.raises(GenerationTimeoutError, match="120-second"):
            await router_mod.generate_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="sys",
                force_provider="ollama",
            )
