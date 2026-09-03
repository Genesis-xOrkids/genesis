"""Tests must never write to the configured application database.

`.env` points at whatever the application should use, which may be a hosted
database serving real data. Nothing stops a test from committing to it except
the binding in the root conftest, so that binding is itself asserted here.

Without this, the failure is silent and only noticed later: a test run leaves
rows in a real database, and the tests still pass.
"""

from __future__ import annotations

from api.genesis_api import db
from api.genesis_api.settings import settings

LOCAL_HOSTS = {"localhost", "127.0.0.1"}


def test_the_test_engine_is_bound_to_the_test_database() -> None:
    assert db.engine().url.host in LOCAL_HOSTS, (
        "tests are bound to a non-local database; the root conftest should have "
        "pointed them at settings.test_database_url"
    )


def test_the_test_database_is_not_the_application_database() -> None:
    """They may coincide locally, but a hosted app database must not be reused."""
    hosted_markers = ("neon.tech", "rds.amazonaws.com", "aws.neon.tech")
    if any(marker in settings.database_url for marker in hosted_markers):
        assert settings.test_database_url != settings.database_url
        assert not any(marker in settings.test_database_url for marker in hosted_markers)
