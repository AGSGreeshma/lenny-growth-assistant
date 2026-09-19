# Agent Transcript 11 — "The Transcripts Don't Provide Enough Information" (While Answering Correctly)

## Problem

While using the deployed app directly, a real answer came back looking like
this:

> "The available transcripts do not provide enough information to answer
> how a startup should find product-market fit. However, according to the
> transcripts, Todd Jackson and Lenny Rachitsky discuss the importance of
> finding product-market fit... Therefore, based on the available
> information, it is not possible to provide a clear and useful answer to
> the user's question."

`grounded: true`, 5 real sources scoring 0.64-0.74, one of them literally
titled "A framework for finding product-market fit | Todd Jackson (First
Round Capital)" — and the model still opened and closed the answer with a
denial, sandwiching genuinely correct, specific synthesis (Todd Jackson's
framework, Rahul from Superhuman, Lenny's benchmarking series) in between.
This reads as broken or as if retrieval silently failed, even though the
underlying data was fine.

## Investigation

First ruled out retrieval as the cause: pulled the raw retrieved chunks
directly (bypassing the LLM) for the exact same query. Four of the five
were genuinely on-topic and substantive — including a chunk that's the
opening of the "framework for finding product-market fit" episode. One
(Manik Gupta, ironically the *highest*-scoring at 0.74) was tangential
("company product fit," not product-*market* fit, and explicitly "I
wouldn't say for startups"), but that alone doesn't explain a model
refusing to answer using the other four.

Reproduced the exact failure directly against Ollama, feeding it the real
retrieved context and the production system prompt (`app/rag/generator.py`)
outside the API, to rule out anything web/session-specific. It reproduced
reliably: the model correctly extracted specific facts (Todd Jackson's four
levels of PMF, Benjamin Lauzier's marketplace advice) but still bookended
them with "the available transcripts do not provide enough information" /
"they do not offer a clear, direct answer."

Root cause: the system prompt's own instruction —

> "If the context does not contain enough information to answer, say that
> the available transcripts do not provide enough information."

This was written before `app/rag/retriever.py`'s hard similarity floor
existed. Today, by the time the LLM is even called, the retriever has
*already* filtered out ungrounded queries structurally (`generate_answer()`
returns `NOT_GROUNDED_MESSAGE` with zero LLM calls when nothing clears the
floor — see transcript 06). The instruction telling the model to
self-assess and hedge about insufficient context is now redundant with a
decision that's already been made upstream — and worse, actively harmful:
a small (3B) local model, given an explicit permission slip to hedge,
reaches for it defensively even when it has perfectly usable material,
producing an answer that contradicts itself.

## Fix

Rewrote `SYSTEM_PROMPT` in `app/rag/generator.py` to remove the
"say when insufficient" instruction entirely and replace it with an
explicit statement that the filtering has already happened — the model's
job is to synthesize, not to re-judge relevance. Verified with an A/B test
using the identical retrieved context and question against real Ollama:
the old prompt produced the hedge-sandwiched answer (reproducible, not a
one-off); the revised prompt produced a direct, confident, correctly-cited
answer with no hedging, using the same underlying facts. Rebuilt the
running Docker backend and re-ran the exact same question through the real
API end-to-end — same result, and ~40% faster (13.4s vs 24.5s), consistent
with the model no longer spending output tokens on redundant disclaimers.

## Lesson

An instruction can be individually reasonable and still become a bug once
the system around it changes — this prompt line was correct when written
(the only grounding signal), and became actively counterproductive once a
structural grounding floor was added elsewhere and made it redundant.
"Grounded: true, but the model still says it doesn't know" is a strong
signal to check whether an upstream safety net and a downstream prompt
instruction are now fighting each other, not to assume retrieval is broken.
