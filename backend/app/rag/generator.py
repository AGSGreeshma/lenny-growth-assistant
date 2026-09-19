from app.llm.router import generate_with_fallback

SYSTEM_PROMPT = """
You are Lenny's Growth Assistant, grounded in real Lenny's Podcast transcripts.

The context below has already been filtered to passages relevant to the
user's question -- you do not need to second-guess whether it is relevant,
or disclaim that the transcripts "don't provide enough information." That
determination has already been made before you were asked to answer; your
job now is to actually answer using what's there.

Synthesize a clear, direct, useful answer from what the guests actually
said. Combine the sources into a real answer to the question -- do not just
summarize each source one by one, and do not hedge with disclaimers about
completeness.

If one source is less relevant than the others, simply draw more from the
better ones -- do not comment on which sources were or weren't useful.

Do not invent facts or attribute claims to guests who did not make them.
When useful, mention the guest/episode a specific point came from.
"""

# Returned when the retriever finds nothing above the similarity floor
# (app/rag/retriever.py). This is a deterministic, structural "I don't know"
# rather than something the LLM is merely asked to say -- a 3B local model
# won't always phrase a refusal the same way twice, so grounding cannot
# safely depend on pattern-matching the model's prose (the previous
# implementation checked for a literal substring in the answer text). No LLM
# call is made in this path at all: there is nothing grounded to hand it.
NOT_GROUNDED_MESSAGE = (
    "I don't have enough grounded material in Lenny's Podcast transcripts to "
    "answer that confidently. Try rephrasing, or ask about a product, growth, "
    "startup, or leadership topic guests have actually discussed on the show."
)


async def generate_answer(
    question: str,
    retrieved_chunks: list[dict],
    history: list[dict] | None = None,
    force_provider: str | None = None,
) -> tuple[str, str]:
    if not retrieved_chunks:
        return NOT_GROUNDED_MESSAGE, "none"

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

    messages = []
    if history:
        messages.extend(history[-4:])
    messages.append({"role": "user", "content": user_prompt})

    return await generate_with_fallback(
        messages=messages, system_prompt=SYSTEM_PROMPT, force_provider=force_provider
    )
