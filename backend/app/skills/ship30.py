"""
Ship 30 for 30 skill: turns grounded transcript material into a ~1,250-word
essay following the Ship 30 for 30 writing framework (strong hook, skimmable
formatting, concrete takeaway). This is a dedicated skill with its own system
prompt and formatting rules -- not a generic one-off prompt tacked onto the
regular Q&A flow -- so its structural requirements are encoded once and
enforced consistently.
"""

from app.llm.router import generate_with_fallback

SHIP30_SYSTEM_PROMPT = """You are an expert ghostwriter trained in the Ship 30 \
for 30 methodology (atomic essays: one clear idea, tightly argued, highly \
skimmable).

Transform the provided source transcript material into a high-impact, \
actionable essay.

Structural requirements:
1. Target length: approximately 1,250 words.
2. The Hook (first 2-3 lines): open with a counterintuitive product/growth \
truth or an urgent operational tension -- not a generic introduction.
3. Formatting: use Markdown. Short paragraphs (1-3 sentences). Clear H2/H3 \
headers. Bold anchor words at the start of bullet points. Use bullet lists \
and section dividers liberally -- this must be skimmable in under a minute.
4. Grounded substance: draw strictly on the insights in the provided context. \
Attribute specific strategies to the guest/episode they came from wherever \
possible.
5. Actionable conclusion: end with a concrete checklist or step-by-step \
framework the reader can apply immediately.

Do not invent facts or attribute ideas to guests who did not say them. If the \
provided context is thin, write a shorter, honest essay rather than padding \
with invented specifics."""


def build_ship30_context(retrieved_chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(retrieved_chunks, start=1):
        parts.append(
            f"""--- SOURCE {i} ---
Episode: {chunk.get("episode", "Unknown")}
Guest: {chunk.get("speaker") or chunk.get("guest") or "Unknown"}

{chunk.get("text", "")[:2500]}"""
        )
    return "\n\n".join(parts)


async def generate_ship30_essay(
    topic: str, retrieved_chunks: list[dict], force_provider: str | None = None
) -> tuple[str, str]:
    """Returns a Markdown-formatted Ship 30 for 30 essay grounded in the
    given transcript chunks. Raises RuntimeError if generation fails
    (propagated from generate_with_fallback, same failure mode as the main
    Q&A path)."""
    context = build_ship30_context(retrieved_chunks)

    user_prompt = f"""Topic / question to build the essay around:
{topic}

Retrieved podcast context:
{context}

Write the Ship 30 for 30 essay now, following all structural requirements."""

    return await generate_with_fallback(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=SHIP30_SYSTEM_PROMPT,
        force_provider=force_provider,
    )