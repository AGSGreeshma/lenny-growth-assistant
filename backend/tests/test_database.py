"""
Database startup resilience (app/database.py's ensure_schema): an
unreachable DATABASE_URL must produce a clear, actionable log line before
the failure propagates -- not just a bare SQLAlchemy traceback as the only
explanation a client engineer gets. No real DB connection -- engine.begin()
is mocked to simulate an unreachable database, and the original exception is
still expected to propagate unchanged (fail-fast startup is preserved).
"""

from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

import app.database as database_mod


def test_ensure_schema_logs_clear_message_and_reraises_on_connection_failure(caplog):
    connection_error = OperationalError(
        "SELECT 1", {}, Exception("could not connect to server: Connection refused")
    )

    with patch.object(database_mod, "engine") as mock_engine:
        mock_engine.begin.side_effect = connection_error
        with caplog.at_level("ERROR", logger="lenny-assistant"):
            with pytest.raises(OperationalError):
                database_mod.ensure_schema()

    messages = [r.message for r in caplog.records]
    assert any("Cannot connect to the database at startup" in m for m in messages)
    assert any("DATABASE_URL" in m for m in messages)


def test_ensure_schema_does_not_swallow_unrelated_errors(caplog):
    """The clear-message wrapper is specific to connection failures
    (OperationalError) -- an unrelated failure inside the same block must
    still propagate as itself, not get mislabeled as a connectivity issue."""
    with patch.object(database_mod, "engine") as mock_engine:
        mock_engine.begin.side_effect = ValueError("something unrelated broke")
        with caplog.at_level("ERROR", logger="lenny-assistant"):
            with pytest.raises(ValueError):
                database_mod.ensure_schema()

    messages = [r.message for r in caplog.records]
    assert not any("Cannot connect to the database at startup" in m for m in messages)
