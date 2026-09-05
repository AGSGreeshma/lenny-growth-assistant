from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

model = SentenceTransformer(MODEL_NAME)


def generate_embedding(text: str) -> list[float]:
    """Generate a 384-dimensional embedding for a text chunk."""
    embedding = model.encode(text)

    return embedding.tolist()