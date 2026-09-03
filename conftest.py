"""Test-wide safety: tests never touch the configured application database.

``.env`` points at whatever the app should use, which may be a hosted database
serving a real branch. Without this, every ``pytest`` run would write there, and
the tests that commit rather than roll back would leave rows behind in it.

Binding the engine once here rather than editing each call site means a new test
file cannot opt out by accident.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from api.genesis_api import db
from api.genesis_api.settings import settings


@pytest.fixture(scope="session", autouse=True)
def _bind_test_database() -> None:
    """Point the shared engine at the test database for the whole session."""
    db._engine = db.engine(settings.test_database_url)  # noqa: SLF001 - deliberate override
    try:
        with db._engine.connect() as connection:  # noqa: SLF001
            connection.execute(text("select 1"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"test database unavailable at {settings.test_database_url}: {exc}")
