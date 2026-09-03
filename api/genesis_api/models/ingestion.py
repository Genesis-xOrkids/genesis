"""Ingestion bookkeeping.

Records that fail validation are quarantined here with their error rather than
defaulted into the catalog. A connector run that drops bad rows silently is
indistinguishable from one that had nothing to do, and the difference matters:
a source that changes shape shows up as a spike in this table, not as a catalog
that quietly stopped growing.
"""

from __future__ import annotations

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.genesis_api.models.base import Base, IdMixin, TimestampMixin


class IngestionFailure(IdMixin, TimestampMixin, Base):
    """One source record that could not be normalized.

    Keyed by source and the source's own id so a re-run updates the existing
    row: a record that keeps failing is one row with a fresh ``updated_at``, not
    a new row every night.

    ``payload`` holds the raw source record as the text the connector received.
    It is deliberately opaque - this is the one place the platform stores a
    source's shape, precisely so nothing downstream has to parse it.
    """

    __tablename__ = "ingestion_failures"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="unique_ingestion_failures_source_source_id"),
        Index("ix_ingestion_failures_source", "source"),
    )

    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
