"""Storefronts we read, and the record of reading them.

The registry is a table rather than a configuration file because it is state,
not settings: the runner queries it to decide what to visit, writes back what it
discovered about each source, and the trend pipeline later needs to know which
brands the catalog actually tracks. A file would drift from all three.

Runs are recorded because a source changing shape has to be visible as a number.
A connector that silently stops returning products looks exactly like a brand
that stopped adding them, and only the run history tells them apart.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.genesis_api.models.base import Base, IdMixin, TimestampMixin
from api.genesis_api.models.enums import IngestionRunStatus, SizeSystem, StorefrontRoute


class Storefront(IdMixin, TimestampMixin, Base):
    """One storefront in the ingestion registry."""

    __tablename__ = "storefronts"
    __table_args__ = (
        UniqueConstraint("domain", name="unique_storefronts_domain"),
        Index("ix_storefronts_enabled", "enabled"),
        CheckConstraint("currency is null or currency ~ '^[A-Z]{3}$'", name="currency_iso4217"),
    )

    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    retailer_name: Mapped[str] = mapped_column(String(256), nullable=False)
    # The label the storefront sells. Usually but not always its own: a
    # multi-brand retailer states the brand per product instead.
    brand_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    route: Mapped[StorefrontRoute] = mapped_column(
        SAEnum(StorefrontRoute, name="storefront_route"),
        nullable=False,
        default=StorefrontRoute.unknown,
    )
    route_checked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Read from the storefront's own metadata. Null means we have not looked yet,
    # and the connector refuses to price anything until we have: an amount
    # without its currency is not a fact.
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    # The system bare numeric sizes are quoted in, defaulted from the store's
    # stated country and overridable here when the operator knows better.
    size_system: Mapped[SizeSystem | None] = mapped_column(
        SAEnum(SizeSystem, name="size_system"), nullable=True
    )

    # False takes a storefront out of the rotation without losing what we learned
    # about it, which deleting the row would.
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    last_ingested_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    runs: Mapped[list[IngestionRun]] = relationship(back_populates="storefront", lazy="raise")


class IngestionRun(IdMixin, TimestampMixin, Base):
    """One attempt at reading one storefront.

    Append-only: a run is something that happened, and re-running does not revise
    the previous attempt. Counting runs by status is how a source degrading
    becomes visible before anyone notices the catalog stopped growing.
    """

    __append_only__ = True
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        Index("ix_ingestion_runs_storefront_id_started_at", "storefront_id", "started_at"),
        Index("ix_ingestion_runs_status", "status"),
    )

    storefront_id: Mapped[int] = mapped_column(
        ForeignKey("storefronts.id", name="fk_ingestion_runs_storefront_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[IngestionRunStatus] = mapped_column(
        SAEnum(IngestionRunStatus, name="ingestion_run_status"), nullable=False
    )
    route: Mapped[StorefrontRoute] = mapped_column(
        SAEnum(StorefrontRoute, name="storefront_route"), nullable=False
    )

    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Everything the run saw and everything it wrote. records_seen alongside the
    # write counts is what makes a quarantine rate computable rather than a raw
    # count with no denominator.
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    products_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    offers_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    images_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sizes_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Populated for failed, blocked, and disallowed runs. Null on success.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    storefront: Mapped[Storefront] = relationship(back_populates="runs", lazy="raise")
