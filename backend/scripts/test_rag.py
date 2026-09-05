import asyncio

from app.database import SessionLocal
from app.rag.retriever import TranscriptRetriever
from app.rag.generator import generate_answer


async def main():

    question = "How can I improve product growth?"

    db = SessionLocal()

    try:
        # Retrieve relevant transcript chunks
        retriever = TranscriptRetriever(db)

        chunks = retriever.retrieve_relevant_chunks(
            question,
            top_k=5,
        )

        print(f"Retrieved {len(chunks)} chunks.")

        # Generate answer using Ollama
        answer = await generate_answer(
            question,
            chunks,
        )

        print("\n========== ANSWER ==========\n")
        print(answer)

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())