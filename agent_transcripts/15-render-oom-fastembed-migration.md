# Agent Transcript 15 — Render's 512MiB OOM: Diagnosis, a Staged Fix, and a Bug Found Only by Testing It

## Problem

First Render deployment failed immediately:

```
==> Out of memory (used over 512Mi)
```

with an accompanying "unauthenticated requests to the HF Hub" warning.

## Investigation

Diagnosed before changing anything, per explicit instruction not to guess.
Traced the actual import chain: `app/main.py` → `app.api.chat` →
`app.rag.retriever` → `app.rag.embeddings`, and `embeddings.py` had
`model = SentenceTransformer(MODEL_NAME)` at **module top level** — meaning
the full torch/transformers/sentence-transformers stack loaded the instant
`uvicorn` started, before any request arrived, health check or not.

Measured, not estimated: ran a progressive import script *inside the
actual backend container* (same image Render builds), reading real RSS
from `/proc/self/status` at each stage. `import torch` alone cost ~195MB;
`sentence_transformers`/`transformers` imports another ~192MB; the actual
model weights only ~28MB. Total after one real `encode()` call: **523.9MB**
— already past the 512MiB ceiling with zero concurrent traffic.

## Fix — staged, with a hard gate before touching production

The instruction was explicit: validate empirically at each step, and stop
rather than replace the production path if fastembed's output wasn't
genuinely equivalent.

1. Compared fastembed's ONNX export of the *same* model
   (`sentence-transformers/all-MiniLM-L6-v2`, still 384 dimensions) against
   the existing torch implementation: cosine similarity **1.000000** across
   8 representative queries.
2. Ran actual retrieval against the real 10,246-row Supabase corpus with
   both implementations: my first overlap metric (set intersection)
   reported only "82.5% overlap" — investigated why before trusting it,
   found it was undercounting because the same episode legitimately
   appears twice in one top-5 sometimes, collapsing under `set()`. The
   corrected, position-by-position metric showed **100% identical**
   results (same chunks, same order, same scores) across all 8 queries.
3. Measured fastembed's own footprint the same way: ~279MB isolated.
4. Only then split `embeddings.py` into two functions:
   `generate_embedding()` (unchanged torch path, ingestion-only) and
   `generate_query_embedding()` (new fastembed path, the live
   request-serving retrieval flow) — both lazy-loaded instead of
   module-level, so importing the module no longer pulls either framework
   into memory on its own.

**A second, more concerning number showed up during verification.** The
*full running application* (not the isolated import test) measured
452-463MB, not 279MB — the frameworks I hadn't accounted for (FastAPI,
SQLAlchemy, the orchestrator module, actual HTTP handling) added real
overhead the component-level test didn't capture. Reported this honestly
rather than citing the more flattering isolated number.

**Then a real bug, caught only by testing the rebuilt image, not by
reading the code.** The container logs showed *multiple concurrent* ONNX
model downloads racing each other after a rebuild — overlapping progress
bars, not one clean load. Root cause: `/api/health` is a synchronous `def`
endpoint, which FastAPI runs in a real thread pool. The lazy-load pattern
(`if _query_model is None: ... instantiate ...`) is not thread-safe — a
plain, unguarded check-then-set can be hit by concurrent threads during the
~20s first-load window, each independently starting its own load. Fixed
with a proper double-checked-locking pattern (`threading.Lock`) on both
lazy singletons. Re-measured after the fix: **324MB** under a real,
end-to-end chat request — the race itself had been inflating memory, not
some inherent floor for the full application.

## Lesson

Two things nearly got missed by stopping at "the isolated numbers look
good": the gap between component-level and full-application memory
measurement, and a concurrency bug that only manifests under real request
timing, not single-threaded testing. Both were caught because the rebuilt
image was actually run and its logs actually read, not because the fix was
assumed correct once the numbers on paper looked right.
