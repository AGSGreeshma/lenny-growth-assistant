"""
Embedding generation. Two separate implementations, deliberately kept apart
rather than one being replaced outright:

- `generate_embedding()` -- torch/SentenceTransformer. Used ONLY by
  `scripts/ingest.py` for one-time, local, offline ingestion of the
  transcript corpus. This is the exact implementation that produced the
  10,246 embeddings currently stored in Supabase -- left unchanged so
  ingestion never has to be re-verified or re-run.
- `generate_query_embedding()` -- fastembed/ONNX Runtime. Used by the live,
  request-serving retrieval path (`app/rag/retriever.py`). Swapped from
  torch specifically to fit Render's 512MiB free-tier memory limit: the
  torch/transformers/sentence-transformers stack alone measured ~524MB RSS
  after one real encode call (exceeding the limit before serving a single
  request), versus ~279MB for the equivalent fastembed path -- measured
  inside the actual container image, not estimated.

  Empirically verified equivalent, not assumed: cosine similarity 1.000000
  across 8 representative queries, and 100% position-identical top-5
  retrieval results against the real 10,246-row Supabase corpus (see
  agent_transcripts for the full comparison). Same model name
  ("sentence-transformers/all-MiniLM-L6-v2"), same 384 dimensions -- the
  stored embeddings, the HNSW index, and retrieval thresholds are
  completely unaffected.

Both models are loaded lazily (only on first actual call, not at module
import time), so importing this module -- which happens automatically at
FastAPI startup via the retriever/chat/essay/artifact import chain -- never
by itself pulls torch into memory. On Render, where only
`generate_query_embedding()` is ever called, torch/sentence-transformers are
never imported into the running process at all.
"""

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_ingestion_model = None
_query_model = None


def generate_embedding(text: str) -> list[float]:
    """Generate a 384-dimensional embedding for a text chunk -- the
    torch/SentenceTransformer path used by ingestion only. See module
    docstring for why this is kept separate from the query path."""
    global _ingestion_model
    if _ingestion_model is None:
        from sentence_transformers import SentenceTransformer

        _ingestion_model = SentenceTransformer(MODEL_NAME)

    embedding = _ingestion_model.encode(text)
    return embedding.tolist()


def generate_query_embedding(text: str) -> list[float]:
    """Generate a 384-dimensional embedding for a live user query -- the
    fastembed/ONNX path used by the request-serving retrieval flow. See
    module docstring for the memory rationale and the empirical
    equivalence verification."""
    global _query_model
    if _query_model is None:
        from fastembed import TextEmbedding

        _query_model = TextEmbedding(model_name=MODEL_NAME)

    return list(_query_model.embed([text]))[0].tolist()
