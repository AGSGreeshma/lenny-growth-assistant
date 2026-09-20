"""
GET /api/health (app/main.py): the db/ollama/embedding_model rollup logic.
Ollama reachability and embedding-model loading are mocked so this doesn't
depend on a real Ollama process or on the sentence-transformers model being
downloaded/cached -- only the DB needs to be real (health() calls get_db()
directly rather than through FastAPI's DI, so it always hits the real test
database regardless of the `client` fixture's dependency override).
"""

from unittest.mock import patch

from tests.conftest import requires_db


@requires_db
def test_health_fully_healthy_when_db_ollama_and_embeddings_all_ok(client):
    import app.main as main_module

    with patch.object(main_module, "_check_ollama", return_value=("ok", None)), patch.object(
        main_module, "_check_embedding_model", return_value=("ok", None)
    ):
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["db"]["status"] == "ok"
    assert body["ollama"]["status"] == "ok"
    assert body["embedding_model"]["status"] == "ok"


@requires_db
def test_health_degraded_when_ollama_down_but_gemini_configured(client):
    import app.main as main_module

    with patch.object(
        main_module, "_check_ollama", return_value=("unreachable", "connection refused")
    ), patch.object(main_module, "_check_embedding_model", return_value=("ok", None)), patch(
        "app.config.GEMINI_API_KEY", "test-key"
    ):
        response = client.get("/api/health")

    body = response.json()
    assert body["status"] == "degraded"
    assert body["ollama"]["status"] == "unreachable"
    assert body["cloud_fallback_configured"] is True


@requires_db
def test_health_unavailable_when_ollama_down_and_no_cloud_fallback(client):
    import app.main as main_module

    with patch.object(
        main_module, "_check_ollama", return_value=("unreachable", "connection refused")
    ), patch.object(main_module, "_check_embedding_model", return_value=("ok", None)), patch(
        "app.config.GEMINI_API_KEY", ""
    ):
        response = client.get("/api/health")

    body = response.json()
    assert body["status"] == "unavailable"
    assert body["cloud_fallback_configured"] is False


@requires_db
def test_health_unavailable_when_embedding_model_fails_regardless_of_llm_status(client):
    import app.main as main_module

    with patch.object(main_module, "_check_ollama", return_value=("ok", None)), patch.object(
        main_module, "_check_embedding_model", return_value=("unavailable", "model load failed")
    ):
        response = client.get("/api/health")

    body = response.json()
    assert body["status"] == "unavailable"
    assert body["embedding_model"]["status"] == "unavailable"
