"""
LLM provider fallback (app/llm/router.py): Ollama first, OpenAI second, clear
failure when neither works. No real network calls -- both clients are
mocked. This is the behavior the "mandatory local Ollama" and "cloud LLM"
requirements both depend on, and the one place both the plain chat path and
every skill (Ship 30, HTML artifact) share.
"""

from unittest.mock import AsyncMock, patch

import pytest

import app.llm.router as router_mod


@pytest.mark.asyncio
async def test_ollama_success_returns_ollama_provider():
    with patch.object(router_mod, "OllamaClient") as MockOllama:
        MockOllama.return_value.generate = AsyncMock(return_value="hello from ollama")
        answer, provider = await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}], system_prompt="sys"
        )
    assert provider == "ollama"
    assert answer == "hello from ollama"


@pytest.mark.asyncio
async def test_ollama_client_constructed_with_configured_timeout():
    """A real 5-chunk RAG prompt measured ~73s on CPU-only reference
    hardware -- if this regresses back to a too-tight timeout, real chat
    requests fail with a 502 on the mandatory local-only path. Lock in that
    OLLAMA_TIMEOUT_SECONDS is actually threaded through to the client."""
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "OLLAMA_TIMEOUT_SECONDS", 120.0
    ):
        MockOllama.return_value.generate = AsyncMock(return_value="hello from ollama")
        await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}], system_prompt="sys"
        )
    MockOllama.assert_called_once_with(
        base_url=router_mod.OLLAMA_BASE_URL, model=router_mod.OLLAMA_MODEL, timeout_seconds=120.0
    )


@pytest.mark.asyncio
async def test_ollama_failure_falls_back_to_openai():
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "OPENAI_API_KEY", "sk-test"
    ), patch("app.llm.openai_client.OpenAIClient") as MockOpenAI:
        MockOllama.return_value.generate = AsyncMock(side_effect=RuntimeError("connection refused"))
        MockOpenAI.return_value.generate = AsyncMock(return_value="hello from openai")

        answer, provider = await router_mod.generate_with_fallback(
            messages=[{"role": "user", "content": "hi"}], system_prompt="sys"
        )

    assert provider == "openai"
    assert answer == "hello from openai"


@pytest.mark.asyncio
async def test_both_providers_failing_raises_runtime_error():
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "OPENAI_API_KEY", "sk-test"
    ), patch("app.llm.openai_client.OpenAIClient") as MockOpenAI:
        MockOllama.return_value.generate = AsyncMock(side_effect=RuntimeError("ollama down"))
        MockOpenAI.return_value.generate = AsyncMock(side_effect=RuntimeError("openai down"))

        with pytest.raises(RuntimeError):
            await router_mod.generate_with_fallback(messages=[], system_prompt="sys")


@pytest.mark.asyncio
async def test_ollama_failure_with_no_cloud_key_configured_raises_clear_error():
    """This is the mandatory Ollama-only demo path: no OPENAI_API_KEY at all.
    A failure here must be an explicit, actionable RuntimeError -- not a
    silent success or an unrelated exception."""
    with patch.object(router_mod, "OllamaClient") as MockOllama, patch.object(
        router_mod, "OPENAI_API_KEY", None
    ):
        MockOllama.return_value.generate = AsyncMock(side_effect=RuntimeError("ollama down"))

        with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
            await router_mod.generate_with_fallback(messages=[], system_prompt="sys")


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
