"""Test fixtures.

Tests run against a real Postgres with pgvector, not SQLite: the schema uses
native enums, check constraints, and a vector column, and a test that cannot see
those is testing a different database than production.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.engine import Connection

from api.genesis_api.db import engine


@pytest.fixture
def connection() -> Iterator[Connection]:
    with engine().connect() as conn:
        yield conn
