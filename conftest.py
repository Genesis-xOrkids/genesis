"""Test-wide safety: tests never touch the configured application database.

``.env`` points at whatever the app should use, which may be a hosted database
serving a real branch. Without this, every ``pytest`` run would write there, and
the tests that commit rather than roll back would leave rows behind in it.

Binding the engine once here rather than editing each call site means a new test
file cannot opt out by accident.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.genesis_api import db
from api.genesis_api.db import engine
from api.genesis_api.settings import settings


@pytest.fixture(scope="session", autouse=True)
def _bind_test_database() -> None:
    """Point the shared engine at the test database for the whole session."""
    db._engine = db.engine(settings.test_database_url)  # noqa: SLF001 - deliberate override
    try:
        with db._engine.connect() as connection:  # noqa: SLF001
            connection.execute(text("select 1"))
    # Blind on purpose: any failure to reach the database means the same thing
    # here, and naming the driver's exception types would couple this guard to
    # the driver.
    except Exception as exc:  # noqa: BLE001  # pragma: no cover
        pytest.skip(f"test database unavailable at {settings.test_database_url}: {exc}")


@pytest.fixture
def session() -> Iterator[Session]:
    """A session rolled back after each test, so tests never see each other.

    It lives here rather than in a package's own conftest because both test
    packages need exactly this, and three copies of a rollback fixture is three
    chances for one of them to start committing.
    """
    connection = engine().connect()
    transaction = connection.begin()
    sess = Session(bind=connection, expire_on_commit=False)
    try:
        yield sess
    finally:
        sess.close()
        transaction.rollback()
        connection.close()
