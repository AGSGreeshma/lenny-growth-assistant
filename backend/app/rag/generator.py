import httpx

from app.config import OLLAMA_BASE_URL, OPENAI_API_KEY
from app.llm.openai_client import OpenAIClient


OLLAMA_MODEL = "llama3.1"

SYSTEM_PROMPT = """
You are Lenny's Growth Assistant.

Answer the user's question using ONLY the information provided
in the retrieved podcast transcript context.

If the context does not contain enough information to answer,
say that the available transcripts do not provide enough information.

Do not invent facts.

Give a clear, useful answer.

When possible, mention the relevant podcast episode title.
"""


async def generate_answer(
    question: str,
    retrieved_chunks: list[dict],
    history: list[dict] | None = None,
) -> str:
    """
    Generate a grounded answer using Ollama first, with OpenAI
    as a fallback if Ollama is unavailable.
    """

    # Build a compact transcript context.
    # Keeping this smaller reduces local-model prompt processing time.
    context_parts = []

    for i, chunk in enumerate(retrieved_chunks, start=1):
        context_parts.append(
            f"""
SOURCE {i}

Episode: {chunk.get("episode", "Unknown")}
Speaker: {chunk.get("speaker") or chunk.get("guest") or "Unknown"}
Timestamp: {chunk.get("timestamp") or "Unknown"}

{chunk.get("text", "")[:1800]}
"""
        )

    context = "\n".join(context_parts)

    user_prompt = f"""
User question:

{question}

Retrieved podcast context:

{context}

Answer the user's question using the retrieved context.
"""

    # Keep only the most recent conversation messages.
    # This preserves follow-up context without making the prompt unnecessarily large.
    messages = []

    if history:
        messages.extend(history[-4:])

    messages.append(
        {
            "role": "user",
            "content": user_prompt,
        }
    )

    # --------------------------------------------------
    # 1. Try Ollama first
    # --------------------------------------------------

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ] + messages,
        "stream": False,
        "keep_alive": "30m",
    }

    try:
        timeout = httpx.Timeout(
            180.0,
            connect=5.0,
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )

            response.raise_for_status()

            data = response.json()

            answer = data.get("message", {}).get("content")

            if not answer:
                raise RuntimeError("Ollama returned an empty response.")

            return answer

    except Exception:
        # Ollama failed, so continue to OpenAI fallback.
        pass

    # --------------------------------------------------
    # 2. Fall back to OpenAI
    # --------------------------------------------------

    if not OPENAI_API_KEY:
        raise RuntimeError(
            "Ollama failed and OPENAI_API_KEY is not configured."
        )

    try:
        openai_client = OpenAIClient()

        return await openai_client.generate(
            messages=messages,
            system_prompt=SYSTEM_PROMPT,
        )

    except Exception as exc:
        raise RuntimeError(
            f"Both Ollama and OpenAI generation failed: {exc}"
        ) from exc