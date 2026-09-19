import asyncio
import json
import re

import httpx


def _trim_to_sentence_boundary(text: str) -> str:
    """Cuts soft-deadline-truncated content back to the last clean
    sentence/paragraph ending, so a mid-generation cutoff reads as an
    intentionally shorter response rather than text stopping mid-word.
    Falls back to the raw text if no good boundary is found in roughly the
    back half of it.

    Requires at least two letters immediately before the punctuation, not
    just any `[.!?]` -- otherwise a numbered-list marker like "**1." (a very
    common place for Markdown generation to be cut off, right after
    starting a new list item) looks like a valid sentence ending and gets
    kept, leaving a dangling "1." at the end of the trimmed response. This
    was caught during live verification, not written defensively upfront."""
    last_end = None
    for match in re.finditer(r"[A-Za-z]{2,}[.!?](?:\s|$)", text):
        last_end = match
    if last_end and last_end.end() > len(text) * 0.5:
        return text[: last_end.end()].rstrip()
    return text.rstrip()


class OllamaClient:

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2:3b",
        timeout_seconds: float = 60.0,
        num_ctx: int = 8192,
        num_predict: int = 3000,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.num_ctx = num_ctx
        self.num_predict = num_predict

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> tuple[str, bool]:
        """Streams the response from Ollama and enforces `timeout_seconds`
        as a SOFT wall-clock budget for the whole generation, rather than a
        hard connection-level timeout on a single buffered response.
        Long-form generation on CPU-only hardware can genuinely take longer
        than the budget allows; reading token-by-token means that when the
        budget runs out, whatever coherent content has already been
        generated is returned (trimmed to a clean sentence boundary)
        instead of being discarded, which is what a non-streaming request
        would do on timeout.

        The budget is enforced with `asyncio.wait_for` around the whole
        read, not a per-chunk httpx read timeout: a per-chunk timeout can't
        tell a genuinely slow generation apart from Ollama's own
        prompt-processing phase, which happens before any token is emitted
        at all and can itself take a long time on CPU for a large
        RAG-retrieved context -- an earlier version of this used a
        per-chunk timeout and it misfired during exactly that phase,
        treating normal (if slow) prompt evaluation as a hang. `wait_for`
        measures actual total elapsed time regardless of which phase it's
        spent in, and cancellation still leaves whatever was already
        appended to `content_parts` intact for the caller to use.

        Returns (content, hit_deadline) -- hit_deadline is True if the soft
        budget was reached before Ollama reported the response as done."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt}
            ] + messages,
            "stream": True,
            "keep_alive": "30m",
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }

        content_parts: list[str] = []

        async def _read_stream() -> None:
            # Generous on purpose -- this is a last-resort backstop against
            # a genuinely dead connection (no bytes at all, ever), not the
            # soft generation budget. asyncio.wait_for below is what
            # actually enforces `timeout_seconds`, and will cancel this
            # coroutine well before this fires in the normal "still
            # generating" case.
            timeout = httpx.Timeout(self.timeout_seconds + 60.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        chunk = json.loads(line)
                        piece = chunk.get("message", {}).get("content", "")
                        if piece:
                            content_parts.append(piece)
                        if chunk.get("done"):
                            return

        hit_deadline = False
        try:
            await asyncio.wait_for(_read_stream(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            hit_deadline = True

        content = "".join(content_parts)
        if hit_deadline:
            content = _trim_to_sentence_boundary(content)
        return content, hit_deadline
