"""
Ship 30 for 30 skill: turns grounded transcript material into an
approximately 1,240-1,250-word essay following the Ship 30 for 30 writing
framework (strong hook, skimmable formatting, concrete takeaway). This is a
dedicated skill with its own system prompt and formatting rules -- not a
generic one-off prompt tacked onto the regular Q&A flow -- so its
structural requirements are encoded once and enforced consistently.

ENGINEERING DECISION: this generation runs against the local, CPU-bound
Ollama path (see app/llm/router.py and app/config.py's OLLAMA_TIMEOUT_SECONDS
comment) as its mandatory demo path. The ~1,240-1,250-word length is this
skill's IDEAL content target, not something worth exceeding the generation
time budget to reach. The prompt below deliberately ranks groundedness,
relevance, and coherence above hitting an exact word count, and explicitly
tells the model not to pad -- a shorter, complete, honest essay is the
correct output when the runtime budget (or the available grounded material)
doesn't support the full target length. See docs/architecture.md's
"Ship 30 for 30 length vs. local-model latency" section for the full
trade-off writeup.
"""

from app.llm.router import generate_with_fallback

SHIP30_SYSTEM_PROMPT = """You are an expert ghostwriter trained in the Ship 30 \
for 30 methodology (atomic essays: one clear idea, tightly argued, highly \
skimmable).

Transform the provided source transcript material into a high-impact, \
actionable essay. This runs on a local model under a runtime budget, so \
prioritize your effort in exactly this order -- earlier items matter more \
than later ones:
1. Groundedness and factual accuracy -- every claim traces to the provided \
source material. Never invent a fact, statistic, company, product, or case \
study that isn't explicitly in the provided context.
2. Relevance -- directly answer the topic given, using the sources that \
actually speak to it.
3. Coherent narrative -- a clear line from the Hook through to the \
Conclusion, not a disconnected list of facts.
4. Useful insights and takeaways -- specific, applicable points, not \
generic advice restated from the prompt.
5. Good structure and readability -- skimmable Markdown (see formatting \
rules below).
6. Reasonable long-form length -- aim for approximately 1,240-1,250 words \
as the ideal target.
7. Exact word-count adherence -- least important. Never pad, repeat a point \
in different words, or add a filler section just to move the count closer \
to 1,250. If the essay is coherent, grounded, and complete at a shorter \
length, that is the correct output -- stop there rather than stretching it.

Structural requirements:
1. The Hook (first 2-3 lines): open with a counterintuitive product/growth \
truth or an urgent operational tension -- not a generic introduction.
2. Formatting: use Markdown. Short paragraphs (1-3 sentences). Clear H2 \
headers, one per major source/idea (the user message tells you how many \
sources were retrieved). Bold anchor words at the start of bullet points. \
Use bullet lists and section dividers liberally -- this must be skimmable \
in under a minute.
3. Grounded substance: draw strictly on the insights in the provided \
context. Attribute specific strategies to the guest/episode they came from \
wherever possible. When unpacking a section, ground each point in what \
that source actually said -- do not invent a company name, product, or case \
study to illustrate it unless that same example already appears in the \
provided source text.
4. Actionable conclusion: end with a concrete checklist or step-by-step \
framework the reader can apply immediately, drawn from what was actually \
covered above -- not a generic wrap-up.

If the provided context is too thin to support a full essay without \
inventing detail, write a shorter, honest essay instead. A complete, \
grounded essay that falls short of the ideal length is always preferable to \
a longer one that pads, repeats itself, or invents specifics to fill space."""


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
    given transcript chunks. Raises RuntimeError (or the more specific
    GenerationTimeoutError) if generation fails, propagated from
    generate_with_fallback -- same failure mode as the main Q&A path. A
    response that's shorter than the ~1,250-word ideal because the local
    model's runtime budget ran out is not a failure; see
    app/llm/router.py's soft-deadline handling."""
    context = build_ship30_context(retrieved_chunks)

    section_count = max(len(retrieved_chunks), 1)
    guest_names = [
        chunk.get("speaker") or chunk.get("guest") or f"Source {i}"
        for i, chunk in enumerate(retrieved_chunks, start=1)
    ] or ["the guest"]

    user_prompt = f"""Topic / question to build the essay around:
{topic}

Retrieved podcast context ({section_count} sources, covering {", ".join(guest_names)}):
{context}

Write the Ship 30 for 30 essay now: the Hook, then one H2 section per source \
above covering that source's idea, then a Conclusion with the actionable \
checklist. Follow the priority order and structural requirements from your \
instructions -- groundedness and coherence come first, the ~1,240-1,250-word \
target is the last priority and is not worth padding to reach."""

    return await generate_with_fallback(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=SHIP30_SYSTEM_PROMPT,
        force_provider=force_provider,
    )
