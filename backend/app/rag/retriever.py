from sqlalchemy import text

from app.rag.embeddings import generate_embedding

# Cosine-similarity floor below which a retrieved chunk is treated as noise
# rather than evidence. This is what lets the system say "I don't know"
# structurally instead of relying on the LLM happening to phrase an
# "insufficient information" sentence a certain way (see
# app/rag/generator.py). It is a heuristic, not a proven-optimal cutoff.
#
# Measured against the real, fully-ingested corpus (scripts/probe_retrieval_threshold.py):
# - Specific, clearly in-domain questions ("How should a startup find
#   product-market fit?") score 0.55-0.74 -- comfortable margin above 0.30.
# - Vague/generic messages ("ok thanks", "tell me more about that") mostly
#   score 0.20-0.33 -- close to the floor, occasionally crossing it.
# - Topics adjacent to but not really covered by the corpus (personal taxes,
#   choosing a programming language, marathon training) consistently score
#   0.32-0.46 -- i.e. *higher* than some genuinely in-domain-but-plainly-
#   phrased questions below.
# - Some genuinely in-domain questions phrased plainly ("Is it better to
#   raise a big round or stay lean?", "What did guests say about burnout?")
#   score only 0.28-0.44 -- in the *same* band as the adjacent-topic noise
#   above.
#
# In other words: a single global cosine-similarity threshold cannot cleanly
# separate "adjacent but not covered" from "genuinely in-domain but plainly
# phrased" -- they overlap in the 0.30-0.45 range. Raising the floor to
# reject more borderline-adjacent topics would also reject real, answerable
# questions (verified: 0.45 drops the burnout example to 0/5 retrieved
# chunks). Kept at 0.30 deliberately: it correctly rejects clearly
# out-of-domain queries and preserves recall on real questions, accepting
# that some borderline-adjacent topics will occasionally clear the floor --
# the system prompt's grounding instruction is the second line of defense
# for that band (see app/rag/generator.py's SYSTEM_PROMPT), and was observed
# in practice to correctly decline to answer from weak context even when the
# floor let it through. Tunable via RAG_MIN_SIMILARITY in .env.example.
DEFAULT_MIN_SIMILARITY = 0.30


class TranscriptRetriever:

    def __init__(self, db):
        self.db = db

    def retrieve_relevant_chunks(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ):
        """Returns the top-k transcript chunks for `query`, filtered to those
        scoring at or above `min_similarity`. An empty result means the
        knowledge base has no evidence for this query above the relevance
        floor -- callers should treat that as "not grounded", not as "zero
        chunks happened to exist"."""
        # 1. Convert the user's question into a vector
        query_vector = generate_embedding(query)

        # 2. Search Supabase using pgvector cosine similarity. We still fetch
        # top_k unfiltered from SQL (cheap: pgvector's index does the real
        # work) and apply the relevance floor in Python -- simpler than a
        # second CAST(:vector AS vector) expression in a WHERE clause, and
        # top_k is small enough that this costs nothing measurable.
        sql = text("""
            SELECT
                episode_title,
                episode_url,
                chunk_text,
                speaker,
                timestamp,
                1 - (embedding <=> CAST(:vector AS vector)) AS similarity_score
            FROM transcript_chunks
            ORDER BY embedding <=> CAST(:vector AS vector)
            LIMIT :limit
        """)

        result = self.db.execute(
            sql,
            {
                "vector": str(query_vector),
                "limit": top_k,
            },
        )

        rows = result.fetchall()

        # 3. Convert database results into Python dictionaries, dropping
        # anything below the relevance floor.
        chunks = [
            {
                "episode": row.episode_title,
                "url": row.episode_url,
                "text": row.chunk_text,
                "speaker": row.speaker,
                "timestamp": row.timestamp,
                "score": float(row.similarity_score),
            }
            for row in rows
        ]
        return [c for c in chunks if c["score"] >= min_similarity]
