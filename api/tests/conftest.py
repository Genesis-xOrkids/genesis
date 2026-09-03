"""Test fixtures.

Tests run against a real Postgres with pgvector, not SQLite: the schema uses
native enums, check constraints, and a vector column, and a test that cannot see
those is testing a different database than production.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from api.genesis_api.db import engine


@pytest.fixture(scope="session", autouse=True)
def _require_database() -> None:
    try:
        with engine().connect() as connection:
            connection.execute(text("select 1"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")


@pytest.fixture
def connection() -> Iterator[Connection]:
    with engine().connect() as conn:
        yield conn


@pytest.fixture
def session() -> Iterator[Session]:
    """A session rolled back after each test, so tests never see each other."""
    connection = engine().connect()
    transaction = connection.begin()
    sess = Session(bind=connection, expire_on_commit=False)
    try:
        yield sess
    finally:
        sess.close()
        transaction.rollback()
        connection.close()
