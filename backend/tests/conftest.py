"""
Shared pytest fixtures.

Two tiers of tests live in this suite:

1. Pure-Python / mocked-boundary tests (test_sanitizer.py, test_router_fallback.py,
   test_orchestrator_routing.py, test_retriever_threshold.py, test_schemas.py) --
   no database, no network. These always run.
2. API-level tests (test_api_*.py) that exercise the real FastAPI app against a
   real Postgres+pgvector database, because app/models/db_models.py uses
   Postgres-specific column types (UUID, JSONB, pgvector's Vector) that a
   SQLite substitute cannot represent. These need a reachable test database --
   see README.md's "Running tests" section for how to start one (the
   docker-compose Postgres service works fine as the test DB too). If no
   database is reachable, these tests are skipped with a clear reason rather
   than failing the whole suite or silently passing.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Force a predictable, side-effect-free configuration for every test unless a
# test explicitly overrides it. AGENT_SDK_ENABLED=false keeps routing tests
# deterministic (no attempt to shell out to the `claude` CLI) unless a test
# is specifically exercising that path with mocks.
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/lenny_test"),
)
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("AGENT_SDK_ENABLED", "false")
os.environ.setdefault("OPENAI_API_KEY", "")

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


def _db_reachable(url: str) -> bool:
    try:
        from sqlalchemy import create_engine

        engine = create_engine(url)
        with engine.connect():
            return True
    except Exception:
        return False


DB_AVAILABLE = _db_reachable(TEST_DATABASE_URL)

requires_db = pytest.mark.skipif(
    not DB_AVAILABLE,
    reason=(
        f"No reachable Postgres test database at {TEST_DATABASE_URL}. "
        "Start one (e.g. `docker compose up -d db`) or set TEST_DATABASE_URL, "
        "then re-run pytest. See README.md's 'Running tests' section."
    ),
)


@pytest.fixture(scope="session")
def db_engine():
    if not DB_AVAILABLE:
        pytest.skip("test database not reachable")

    from app.database import Base, ensure_schema

    ensure_schema()  # creates extensions + all tables against TEST_DATABASE_URL
    from app.database import engine

    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session(db_engine):
    from sqlalchemy.orm import sessionmaker

    TestingSessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        from app.database import Base

        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()


@pytest.fixture()
def client(db_session):
    """A FastAPI TestClient wired to the per-test db_session, so each test
    sees an isolated (empty-before-and-after) set of tables."""
    from fastapi.testclient import TestClient

    import app.main as main_module
    from app.database import get_db

    def _override_get_db():
        yield db_session

    main_module.app.dependency_overrides[get_db] = _override_get_db
    with TestClient(main_module.app) as test_client:
        yield test_client
    main_module.app.dependency_overrides.clear()
