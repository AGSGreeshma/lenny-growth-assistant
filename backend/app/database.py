import logging

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

logger = logging.getLogger("lenny-assistant")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)

Base = declarative_base()


def ensure_schema():
    """Make the database usable on a fresh instance with zero manual steps
    (part of the one-command Docker Compose startup story), and apply
    additive schema fixes that create_all will not add to already-existing
    tables.

    Previously this only ran the ALTER TABLE fixes below and relied on
    someone having already run backend/create_tables.py by hand -- which
    meant `docker compose up` alone left the backend crash-looping against a
    database with no tables at all. create_all() is idempotent (a no-op for
    tables that already exist), so it's safe to run on every startup.
    create_tables.py is kept as a standalone manual alternative (e.g. for
    running migrations separately from the app process), but is no longer
    required.
    """
    # Import here, not at module level: app.models.db_models imports Base
    # from this module, so importing it up top would be a circular import.
    # This is also the only thing that registers TranscriptChunk/ChatSession/
    # ChatMessage on Base.metadata before create_all() runs.
    from app.models import db_models  # noqa: F401

    # This is the first point `ensure_schema()` actually opens a connection --
    # if DATABASE_URL is unreachable (wrong host/port, DB not running, bad
    # credentials), `engine.begin()` itself raises here, before the inner
    # try/except below ever runs. The behavior on failure is deliberately
    # fail-fast (see this function's docstring) -- this wrapper only makes
    # the failure's *presentation* clear (a one-line, actionable summary
    # naming the cause) instead of a bare SQLAlchemy traceback being the only
    # explanation a client engineer gets. It re-raises the original
    # exception unchanged, so the full technical traceback for real
    # debugging is still there, right after the summary.
    try:
        with engine.begin() as conn:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            except Exception:
                # Managed Postgres (e.g. some Supabase plans) may already have
                # these enabled and restrict CREATE EXTENSION for the app's role.
                # Don't fail startup over it -- log and let create_all proceed;
                # it will fail loudly and specifically if the extension truly
                # isn't available.
                logger.warning(
                    "Could not CREATE EXTENSION vector/pgcrypto (may already be "
                    "enabled, or the DB role lacks privileges). Continuing."
                )
    except OperationalError as exc:
        logger.error(
            "Cannot connect to the database at startup. Check that "
            "DATABASE_URL is correct and the database is actually reachable "
            "(host, port, credentials, and that Postgres itself is running) "
            "-- see the traceback below for the underlying driver error: %s",
            exc,
        )
        raise

    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS artifact_type TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS client_label TEXT"
        ))
        # SQLAlchemy's Base.metadata.create_all() above only knows about
        # columns/tables declared on the model -- it has no idea an HNSW
        # index should exist on transcript_chunks.embedding, since that
        # index isn't expressible as a plain column attribute. Without this,
        # a database that only ever went through ensure_schema() (e.g. a
        # fresh `docker compose up` run) would silently get zero vector
        # index and fall back to a sequential scan on every retrieval.
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS transcript_chunks_embedding_idx "
            "ON transcript_chunks USING hnsw (embedding vector_cosine_ops)"
        ))


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
