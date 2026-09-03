"""Engine and session factories.

One engine per process. The read path takes a Core ``Connection``; the write path
takes an ORM ``Session``. They share the schema, not the execution model.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from api.genesis_api.settings import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def engine(url: str | None = None) -> Engine:
    """The application engine, or a one-off engine for an explicit URL.

    Tests pass their own URL so a hosted database configured for the app is
    never written to by a test run.
    """
    if url is not None:
        return create_engine(url, echo=settings.sql_echo, pool_pre_ping=True)
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, echo=settings.sql_echo, pool_pre_ping=True)
    return _engine


def session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=engine(), expire_on_commit=False)
    return _session_factory


@contextmanager
def read_connection() -> Iterator[Connection]:
    """A Core connection for the read path."""
    with engine().connect() as connection:
        yield connection


@contextmanager
def write_session() -> Iterator[Session]:
    """An ORM session for the write path, committed on clean exit."""
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
