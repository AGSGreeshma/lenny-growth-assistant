"""
OllamaClient (app/llm/ollama_client.py): the soft-deadline streaming
behavior underneath the 120s OLLAMA_TIMEOUT_SECONDS engineering decision (see
app/config.py). No real network calls -- a fake NDJSON stream (with small,
real, deliberate delays between chunks) is served through
httpx.MockTransport, and asyncio.wait_for's real cancellation is exercised
directly rather than mocked, since that's the actual mechanism enforcing the
budget (see the "Lesson" in agent_transcripts/13 -- an earlier version of
this used a per-chunk httpx read timeout as the budget, which misfired
during Ollama's prompt-processing phase; the fix is the asyncio.wait_for
wrapper this test exercises for real).
"""

import asyncio

from unittest.mock import patch

import httpx
import pytest

from app.llm import ollama_client as ollama_client_mod
from app.llm.ollama_client import OllamaClient, _trim_to_sentence_boundary

_RealAsyncClient = httpx.AsyncClient


class _DelayedStream(httpx.AsyncByteStream):
    """Yields each NDJSON line after a small real delay, so a deadline
    shorter than the total stream duration genuinely has something to cut
    off mid-stream -- exercising real asyncio cancellation, not a mock."""

    def __init__(self, lines: list[bytes], delay: float):
        self._lines = lines
        self._delay = delay

    async def __aiter__(self):
        for line in self._lines:
            await asyncio.sleep(self._delay)
            yield line + b"\n"


def _ndjson_transport(lines: list[bytes], delay: float) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_DelayedStream(lines, delay))

    return httpx.MockTransport(handler)


def _patched_async_client(transport: httpx.MockTransport):
    def factory(*args, **kwargs):
        return _RealAsyncClient(transport=transport)

    return factory


@pytest.mark.asyncio
async def test_generate_returns_full_response_when_done_before_deadline():
    lines = [
        b'{"message": {"content": "Hello "}, "done": false}',
        b'{"message": {"content": "world."}, "done": true}',
    ]
    transport = _ndjson_transport(lines, delay=0.01)

    with patch.object(
        ollama_client_mod.httpx, "AsyncClient", side_effect=_patched_async_client(transport)
    ):
        client = OllamaClient(timeout_seconds=2.0)
        content, hit_deadline = await client.generate(messages=[], system_prompt="sys")

    assert content == "Hello world."
    assert hit_deadline is False


@pytest.mark.asyncio
async def test_generate_stops_and_trims_at_soft_deadline():
    """The core soft-deadline contract: once the wall-clock budget is spent,
    reading is cancelled (later chunks never arrive) and the content
    gathered so far is returned, trimmed to the last clean sentence, with
    hit_deadline=True -- not an exception, and not the full response."""
    lines = [
        b'{"message": {"content": "Hello "}, "done": false}',
        b'{"message": {"content": "world. "}, "done": false}',
        b'{"message": {"content": "This should never be read. "}, "done": false}',
        b'{"message": {"content": "Neither should this."}, "done": true}',
    ]
    # Each line lands at ~0.1s, 0.2s, 0.3s, 0.4s; a 0.25s deadline cuts off
    # after the second line.
    transport = _ndjson_transport(lines, delay=0.1)

    with patch.object(
        ollama_client_mod.httpx, "AsyncClient", side_effect=_patched_async_client(transport)
    ):
        client = OllamaClient(timeout_seconds=0.25)
        content, hit_deadline = await client.generate(messages=[], system_prompt="sys")

    assert hit_deadline is True
    assert content == "Hello world."
    assert "never be read" not in content
    assert "Neither should this" not in content


@pytest.mark.asyncio
async def test_slow_prompt_processing_before_first_token_is_not_mistaken_for_a_hang():
    """Regression test for the actual bug found during live verification:
    Ollama's prompt-processing phase (before any token streams back) can
    itself take a long time on CPU for a large RAG context. The budget must
    be measured as total elapsed wall-clock time, not as a per-chunk gap --
    a long silent stretch before the FIRST token must not be treated any
    differently than a long gap between later tokens."""
    lines = [
        b'{"message": {"content": "Finally, a token."}, "done": true}',
    ]
    # The single line doesn't land until 0.3s in -- simulating a slow
    # prefill phase -- but the deadline (0.5s) comfortably covers it.
    transport = _ndjson_transport(lines, delay=0.3)

    with patch.object(
        ollama_client_mod.httpx, "AsyncClient", side_effect=_patched_async_client(transport)
    ):
        client = OllamaClient(timeout_seconds=0.5)
        content, hit_deadline = await client.generate(messages=[], system_prompt="sys")

    assert content == "Finally, a token."
    assert hit_deadline is False


def test_trim_to_sentence_boundary_cuts_at_last_clean_ending():
    text = "Hello world. This is a complete sentence. And this is a cut off f"
    assert _trim_to_sentence_boundary(text) == "Hello world. This is a complete sentence."


def test_trim_to_sentence_boundary_falls_back_when_no_good_boundary_found():
    text = "no punctuation anywhere in this fragment at all"
    assert _trim_to_sentence_boundary(text) == text


def test_trim_to_sentence_boundary_does_not_treat_a_list_marker_as_a_sentence_end():
    """Regression test for the exact edge case caught during live
    verification: a cutoff right after '**1.' (a numbered-list marker, not
    a real sentence ending) must not be kept as the trimmed ending."""
    text = "This part is complete and grounded.\n\n**1."
    assert _trim_to_sentence_boundary(text) == "This part is complete and grounded."
