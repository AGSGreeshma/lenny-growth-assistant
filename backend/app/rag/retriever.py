from sqlalchemy import text

from app.rag.embeddings import generate_embedding


class TranscriptRetriever:

    def __init__(self, db):
        self.db = db

    def retrieve_relevant_chunks(
        self,
        query: str,
        top_k: int = 5,
    ):
        # 1. Convert the user's question into a vector
        query_vector = generate_embedding(query)

        # 2. Search Supabase using pgvector cosine similarity
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

        # 3. Convert database results into Python dictionaries
        return [
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