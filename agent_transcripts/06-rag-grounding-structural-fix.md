# Agent Transcript 06 — Making "Not Grounded" a Structural Guarantee

## Problem

The original grounding check worked like this: always retrieve the top-k
nearest chunks from pgvector (regardless of how similar they actually were),
hand them to the LLM, and ask the model to say "the transcripts don't
contain enough information" if the material was thin. Whether an answer
counted as "grounded" was then determined by checking whether the model's
free-text response happened to contain a specific substring.

This has two independent failure modes:

1. **pgvector's `ORDER BY ... LIMIT` always returns *something*.** A
   completely out-of-domain question (nothing to do with product, growth, or
   the podcast at all) still gets back the k *least bad* nearest neighbors —
   which might have a cosine similarity of 0.05 to the query. Handing those
   to the model as "context" invites it to either hallucinate a connection or
   get confused about why irrelevant material was provided.
2. **A 3B local model doesn't reliably phrase a refusal the same way twice.**
   Pattern-matching a specific substring in the model's own prose is fragile
   — a slightly different phrasing of "I don't have enough information"
   silently breaks the "grounded" flag without breaking anything visibly.

## Fix

Two changes, both structural rather than prompt-based:

1. `app/rag/retriever.py`: `TranscriptRetriever.retrieve_relevant_chunks()`
   now drops any chunk scoring below `DEFAULT_MIN_SIMILARITY` (0.30,
   configurable via `RAG_MIN_SIMILARITY`) *before* returning. An
   out-of-domain query with only low-similarity neighbors now returns an
   empty list, not "the least-bad k chunks."
2. `app/rag/generator.py`: `generate_answer()` checks `if not
   retrieved_chunks` and returns a fixed `NOT_GROUNDED_MESSAGE` **with no LLM
   call at all** in that case. `is_grounded` in the API layer
   (`app/api/chat.py`, `essay.py`) is now simply `bool(chunks)` — a property
   of the retrieval step, not something inferred from generated text.

## Trade-off

A fixed similarity floor is a heuristic, not a proven cutoff — a genuinely
relevant but loosely-worded question could score just under 0.30 and get
rejected, and a borderline-relevant one could score just over and get
accepted. `RAG_MIN_SIMILARITY` is exposed as an env var specifically so this
can be tuned against real query logs rather than treated as fixed forever.
The alternative (keep asking the model to self-report) was rejected because
it makes "grounded" an emergent property of prompt-following behavior on a
small model, which is exactly the kind of thing that looks fine in a demo and
breaks unpredictably in front of an evaluator.

## Lesson

When "the model should say X" is doing safety-relevant work, prefer moving
the check into code that runs *before* the model call wherever the
information needed to do so already exists (here: the similarity scores
pgvector already computes). Reserve prompted behavior for things that
genuinely can't be checked structurally.
