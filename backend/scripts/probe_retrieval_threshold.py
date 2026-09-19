"""
Diagnostic tool for tuning RAG_MIN_SIMILARITY (app/rag/retriever.py).

Runs a small, hand-built set of queries spanning four categories --
clearly in-domain, vague/generic, borderline-adjacent, and clearly
out-of-domain -- against the real ingested corpus, and reports the raw
(unfiltered) top-5 cosine-similarity scores for each, plus how many chunks
would clear a range of candidate thresholds.

Use this whenever considering a RAG_MIN_SIMILARITY change: eyeballing a
single query's score is not enough to tell whether a new threshold helps
more than it hurts, because (as this project's real corpus shows) some
genuinely in-domain, plainly-phrased questions score in the same range as
borderline-adjacent, not-really-covered topics. Add representative queries
of your own below as the query set this evaluates is small and specific to
this corpus, not a rigorous benchmark.

Usage:
    cd backend && python scripts/probe_retrieval_threshold.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.rag.retriever import TranscriptRetriever

QUERIES = {
    "in-domain (specific)": [
        "How should a startup find product-market fit?",
        "What makes a great product manager?",
        "How do you prioritize a product roadmap?",
        "How do I improve activation for a B2B SaaS product?",
    ],
    "in-domain (plainly phrased -- false-negative risk if floor is raised)": [
        "Is it better to raise a big round or stay lean?",
        "What did guests say about burnout?",
        "How do you know when to pivot?",
    ],
    "vague / generic (false-positive risk)": [
        "follow up question",
        "can you explain more",
        "tell me more about that",
        "ok thanks",
    ],
    "borderline (adjacent, not clearly covered)": [
        "How do I file my taxes as a small business?",
        "What's the best programming language for beginners?",
        "How do I train for a marathon?",
    ],
    "out-of-domain (should score low)": [
        "What is the boiling point of nitrogen?",
        "How do I fix a flat tire on my car?",
        "What's the recipe for chocolate chip cookies?",
    ],
}

CANDIDATE_THRESHOLDS = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]


def main():
    db = SessionLocal()
    retriever = TranscriptRetriever(db)

    for category, queries in QUERIES.items():
        print(f"\n=== {category} ===")
        for q in queries:
            chunks = retriever.retrieve_relevant_chunks(q, top_k=5, min_similarity=0.0)
            scores = [round(c["score"], 3) for c in chunks]
            passes = " ".join(
                f"{t}:{sum(1 for s in scores if s >= t)}/5" for t in CANDIDATE_THRESHOLDS
            )
            print(f"  {q!r:60} scores={scores}")
            print(f"  {'':60} {passes}")


if __name__ == "__main__":
    main()
