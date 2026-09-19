"""
RAG grounding floor (app/rag/retriever.py): rows below DEFAULT_MIN_SIMILARITY
must be dropped so an out-of-domain question doesn't get "evidence" just
because pgvector always returns *some* nearest neighbours. The DB session and
embedding call are both stubbed -- this only tests the Python-side filtering.
"""

from unittest.mock import MagicMock, patch

from app.rag.retriever import DEFAULT_MIN_SIMILARITY, TranscriptRetriever


def _row(score: float, title: str = "Episode"):
    row = MagicMock()
    row.episode_title = title
    row.episode_url = "https://example.com"
    row.chunk_text = "some transcript text"
    row.speaker = "Guest"
    row.timestamp = "00:01:00"
    row.similarity_score = score
    return row


def _make_db(rows):
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = rows
    return db


@patch("app.rag.retriever.generate_embedding", return_value=[0.0] * 384)
def test_rows_at_or_above_floor_are_kept(mock_embed):
    db = _make_db([_row(0.85, "Strong match"), _row(DEFAULT_MIN_SIMILARITY, "Exactly at floor")])
    retriever = TranscriptRetriever(db)

    chunks = retriever.retrieve_relevant_chunks("what makes a good PM?")

    assert len(chunks) == 2
    assert {c["episode"] for c in chunks} == {"Strong match", "Exactly at floor"}


@patch("app.rag.retriever.generate_embedding", return_value=[0.0] * 384)
def test_rows_below_floor_are_dropped(mock_embed):
    db = _make_db([_row(0.29, "Weak match"), _row(0.05, "Noise")])
    retriever = TranscriptRetriever(db)

    chunks = retriever.retrieve_relevant_chunks("completely unrelated out-of-domain question")

    assert chunks == []


@patch("app.rag.retriever.generate_embedding", return_value=[0.0] * 384)
def test_mixed_scores_only_keeps_rows_above_floor(mock_embed):
    db = _make_db([_row(0.9, "Strong"), _row(0.5, "Medium"), _row(0.1, "Weak")])
    retriever = TranscriptRetriever(db)

    chunks = retriever.retrieve_relevant_chunks("a relevant growth question")

    assert [c["episode"] for c in chunks] == ["Strong", "Medium"]


@patch("app.rag.retriever.generate_embedding", return_value=[0.0] * 384)
def test_no_rows_returns_empty_list(mock_embed):
    db = _make_db([])
    retriever = TranscriptRetriever(db)

    assert retriever.retrieve_relevant_chunks("anything") == []


@patch("app.rag.retriever.generate_embedding", return_value=[0.0] * 384)
def test_custom_min_similarity_overrides_default(mock_embed):
    db = _make_db([_row(0.5, "Medium")])
    retriever = TranscriptRetriever(db)

    assert retriever.retrieve_relevant_chunks("q", min_similarity=0.6) == []
    assert len(retriever.retrieve_relevant_chunks("q", min_similarity=0.4)) == 1


@patch("app.rag.retriever.generate_embedding", return_value=[0.0] * 384)
def test_chunk_dict_shape_matches_downstream_expectations(mock_embed):
    db = _make_db([_row(0.9, "Episode 1")])
    retriever = TranscriptRetriever(db)

    chunks = retriever.retrieve_relevant_chunks("q")

    assert chunks[0].keys() == {"episode", "url", "text", "speaker", "timestamp", "score"}
    assert chunks[0]["score"] == 0.9
