"""Reference and vocabulary tables.

These hold the open vocabularies: values that grow over time (aesthetics, trend
labels, garment details) or that carry their own attributes (brands, retailers).
Closed sets are Postgres enums in ``enums.py`` instead.

Each table has a surrogate integer ``id`` even where a natural key exists: the
GraphQL loader resolves FK-referenced parents by ``.c.id``. The natural key stays
as a unique column so readers can key on it.
"""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.genesis_api.models.base import Base, IdMixin, TimestampMixin
from api.genesis_api.models.enums import PriceTier


class Brand(IdMixin, TimestampMixin, Base):
    """A label a garment carries.

    Distinct from Retailer: Everlane is both, Ganni is a brand sold by many
    retailers, Nordstrom is a retailer carrying many brands.
    """

    __tablename__ = "brands"
    __table_args__ = (
        UniqueConstraint("slug", name="unique_brands_slug"),
        Index("ix_brands_name", "name"),
    )

    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Null means unknown, not "no tier".
    price_tier: Mapped[PriceTier | None] = mapped_column(
        SAEnum(PriceTier, name="price_tier"), nullable=True
    )
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    instagram_handle: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Retailer(IdMixin, TimestampMixin, Base):
    """A place an offer can be bought from."""

    __tablename__ = "retailers"
    __table_args__ = (UniqueConstraint("slug", name="unique_retailers_slug"),)

    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaxonomyValue(IdMixin, TimestampMixin, Base):
    """One value in an open vocabulary.

    ``namespace`` names the vocabulary ("aesthetic", "detail", "material",
    "occasion", "fabric_weight"); ``value`` is the canonical lowercase token.
    Attribute rows on products, wardrobe items, and trend observations point
    here, so a new detail is a row rather than a migration.

    ``season_introduced`` records when a seasonally versioned vocabulary gained
    the value, so a trend series can be read against the vocabulary of its time.
    """

    __tablename__ = "taxonomy_values"
    __table_args__ = (
        UniqueConstraint("namespace", "value", name="unique_taxonomy_values_namespace_value"),
        Index("ix_taxonomy_values_namespace", "namespace"),
    )

    namespace: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    season_introduced: Mapped[str | None] = mapped_column(String(16), nullable=True)
