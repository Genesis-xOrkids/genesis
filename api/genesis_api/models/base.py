"""Declarative base and shared column conventions.

Per CLAUDE.md: models are the schema. These classes define the naming and
timestamp conventions every table inherits; GraphQL types, Alembic migrations,
and the write path all derive from them.
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Named constraints everywhere. Alembic autogenerate emits these names, so a
# constraint never lands in the database with a server-generated name.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "unique_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base for every model. One metadata, one naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    """Integer surrogate primary key.

    Every GraphQL-traversed table has one, including reference and vocabulary
    tables that also carry a natural key: the framework's loader resolves
    FK-referenced parents by ``.c.id``, so a FK must point at ``id``.
    """

    id: Mapped[int] = mapped_column(primary_key=True)


class TimestampMixin:
    """Row lifecycle timestamps.

    These describe the row, not the world. A fact's own time (when a price was
    observed, when a garment was worn) is its own column on the model.
    """

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
