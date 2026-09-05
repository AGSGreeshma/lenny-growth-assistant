from app.database import SessionLocal
from app.rag.retriever import TranscriptRetriever


db = SessionLocal()

try:
    retriever = TranscriptRetriever(db)

    results = retriever.retrieve_relevant_chunks(
        "How can I improve my product growth?",
        top_k=5,
    )

    print(f"\nFound {len(results)} relevant chunks:\n")

    for i, result in enumerate(results, start=1):
        print(f"--- Result {i} ---")
        print(f"Episode: {result['episode']}")
        print(f"Score: {result['score']:.4f}")
        print(f"Text: {result['text'][:500]}")
        print()

finally:
    db.close()