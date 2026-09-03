"""Catalog: products and the offers that make them purchasable.

Source-agnostic. Shopify, Klarna, Rakuten, CJ, Awin and Impact are translated at
the connector boundary into these rows; nothing here references a source's field
names or identifiers beyond the opaque ``source``/``source_id`` natural key that
makes re-syncs idempotent.

A Product is (brand, style, colorway) - the things that change what the item is.
Size and availability change only which unit ships, so they live on Offer.
"""

from __future__ import annotations

import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.genesis_api.models.base import Base, IdMixin, TimestampMixin
from api.genesis_api.models.enums import (
    AttributeSource,
    Category,
    ColorFamily,
    Fit,
    GarmentLength,
    Gender,
    Neckline,
    Pattern,
    Provenance,
    Rise,
    Silhouette,
    SizeSystem,
    SleeveLength,
    SleeveStyle,
)
from api.genesis_api.models.taxonomy import Brand, Retailer, TaxonomyValue

# Marqo FashionSigLIP 2 is built on ViT-B-16-SigLIP: 768-dimensional embeddings.
FASHION_EMBEDDING_DIMS = 768


class Product(IdMixin, TimestampMixin, Base):
    """One purchasable style in one colorway.

    Every attribute column is an atomic fact about the garment. Interpretations
    ("on trend", "flattering", "on sale") are derived where they are used, never
    stored here.
    """

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="unique_products_source_source_id"),
        Index("ix_products_brand_id", "brand_id"),
        Index("ix_products_category", "category"),
        Index("ix_products_color_family", "color_family"),
        CheckConstraint(
            "color_hex is null or color_hex ~ '^#[0-9a-f]{6}$'",
            name="color_hex_format",
        ),
        # HNSW over cosine distance: the catalog is searched by similarity on
        # every stylist turn, and a sequential scan over a few million products
        # is not a search path. Cosine matches how the fashion embedding model
        # was trained, so the operator class is not interchangeable here.
        Index(
            "ix_products_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # Full-text ranking over title and description. Declared here, not only
        # in a migration, so the model stays the single schema authority and
        # autogenerate has something to compare the database against.
        #
        # The expression is written in the exact form Postgres reflects back,
        # including the ::regconfig and ::text casts, because autogenerate
        # compares these as strings: any other spelling is reported as drift on
        # every run. It concatenates with || rather than concat_ws, which is only
        # STABLE and so cannot appear in an index expression, and it is mirrored
        # character for character by the query in intelligence/catalog/search.py.
        Index(
            "ix_products_search_document",
            text(
                "to_tsvector('english'::regconfig, "
                "(title || ' '::text) || COALESCE(description, ''::text))"
            ),
            postgresql_using="gin",
        ),
    )

    # Natural key: the connector's system and its opaque id there. Upserts key
    # on this pair so a re-sync updates rather than duplicates.
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)
    provenance: Mapped[Provenance] = mapped_column(
        SAEnum(Provenance, name="provenance"), nullable=False
    )

    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id", name="fk_products_brand_id"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # First-class garment attributes: the ones the stylist filters on and the
    # trend pipeline scores. The long tail lives in ProductAttribute rows.
    # Null in any of these means unknown, never "not applicable".
    category: Mapped[Category | None] = mapped_column(
        SAEnum(Category, name="category"), nullable=True
    )
    gender: Mapped[Gender | None] = mapped_column(SAEnum(Gender, name="gender"), nullable=True)
    silhouette: Mapped[Silhouette | None] = mapped_column(
        SAEnum(Silhouette, name="silhouette"), nullable=True
    )
    neckline: Mapped[Neckline | None] = mapped_column(
        SAEnum(Neckline, name="neckline"), nullable=True
    )
    sleeve_length: Mapped[SleeveLength | None] = mapped_column(
        SAEnum(SleeveLength, name="sleeve_length"), nullable=True
    )
    sleeve_style: Mapped[SleeveStyle | None] = mapped_column(
        SAEnum(SleeveStyle, name="sleeve_style"), nullable=True
    )
    garment_length: Mapped[GarmentLength | None] = mapped_column(
        SAEnum(GarmentLength, name="garment_length"), nullable=True
    )
    rise: Mapped[Rise | None] = mapped_column(SAEnum(Rise, name="rise"), nullable=True)
    fit: Mapped[Fit | None] = mapped_column(SAEnum(Fit, name="fit"), nullable=True)
    pattern: Mapped[Pattern | None] = mapped_column(SAEnum(Pattern, name="pattern"), nullable=True)

    # The hex is the fact the source or the vision model gives us; the family is
    # a canonical atomic value derived from it, stored alongside and never
    # instead of it.
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    color_family: Mapped[ColorFamily | None] = mapped_column(
        SAEnum(ColorFamily, name="color_family"), nullable=True
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(FASHION_EMBEDDING_DIMS), nullable=True
    )

    brand: Mapped[Brand | None] = relationship(lazy="raise")
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product", lazy="raise", order_by="ProductImage.position"
    )
    materials: Mapped[list[ProductMaterial]] = relationship(back_populates="product", lazy="raise")
    attributes: Mapped[list[ProductAttribute]] = relationship(
        back_populates="product", lazy="raise"
    )
    offers: Mapped[list[Offer]] = relationship(back_populates="product", lazy="raise")


class ProductImage(IdMixin, TimestampMixin, Base):
    """An image of a product, in our own storage.

    Retailer image URLs rot, so the connector copies the bytes to S3 and stores
    the key. ``source_url`` is kept for provenance and re-fetch, not for display.
    """

    __tablename__ = "product_images"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "position", name="unique_product_images_product_id_position"
        ),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", name="fk_product_images_product_id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)

    product: Mapped[Product] = relationship(back_populates="images", lazy="raise")


class ProductMaterial(IdMixin, TimestampMixin, Base):
    """One fiber in a product's composition.

    A garment that is 70% wool / 30% nylon is two rows, not one "70% wool, 30%
    nylon" string: the percentages are independently queryable facts.
    """

    __tablename__ = "product_materials"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "material_id", name="unique_product_materials_product_id_material_id"
        ),
        CheckConstraint("pct is null or (pct > 0 and pct <= 100)", name="pct_range"),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", name="fk_product_materials_product_id", ondelete="CASCADE"),
        nullable=False,
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("taxonomy_values.id", name="fk_product_materials_material_id"), nullable=False
    )
    # Null means the composition listed the fiber without a percentage.
    pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    product: Mapped[Product] = relationship(back_populates="materials", lazy="raise")
    material: Mapped[TaxonomyValue] = relationship(lazy="raise")


class ProductAttribute(IdMixin, TimestampMixin, Base):
    """One long-tail attribute of a product, from an open vocabulary.

    The first-class attributes are columns on Product. Everything else (details,
    occasions, aesthetics, fabric weight) lands here so a new vocabulary value is
    a row rather than a migration. Confidence and source travel with the value:
    a vision model's guess and a merchandiser's label share the column and are
    told apart by ``source``, not by living in different tables.
    """

    __tablename__ = "product_attributes"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "value_id", name="unique_product_attributes_product_id_value_id"
        ),
        Index("ix_product_attributes_value_id", "value_id"),
        CheckConstraint(
            "confidence is null or (confidence >= 0 and confidence <= 1)",
            name="confidence_range",
        ),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", name="fk_product_attributes_product_id", ondelete="CASCADE"),
        nullable=False,
    )
    value_id: Mapped[int] = mapped_column(
        ForeignKey("taxonomy_values.id", name="fk_product_attributes_value_id"), nullable=False
    )
    # Null means the source asserted the value without a confidence.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[AttributeSource] = mapped_column(
        SAEnum(AttributeSource, name="attribute_source"), nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="attributes", lazy="raise")
    value: Mapped[TaxonomyValue] = relationship(lazy="raise")


class Offer(IdMixin, TimestampMixin, Base):
    """A product for sale at a retailer, at a price, right now.

    The listed amount and its currency are the source facts; ``price_usd_cents``
    is the canonical atomic value the backend fills from them, stored alongside
    with the rate that produced it, never instead of them.
    """

    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="unique_offers_source_source_id"),
        Index("ix_offers_product_id", "product_id"),
        Index("ix_offers_retailer_id", "retailer_id"),
        Index("ix_offers_price_usd_cents", "price_usd_cents"),
        CheckConstraint("price_amount_minor >= 0", name="price_amount_minor_nonneg"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso4217"),
    )

    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)
    provenance: Mapped[Provenance] = mapped_column(
        SAEnum(Provenance, name="provenance"), nullable=False
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", name="fk_offers_product_id"),
        nullable=False,
    )
    retailer_id: Mapped[int] = mapped_column(
        ForeignKey("retailers.id", name="fk_offers_retailer_id"), nullable=False
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    # Null means we have no affiliate relationship for this retailer, which is a
    # known state, not an unknown one: the connector writes it explicitly.
    affiliate_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    price_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    sale_price_amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_usd_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fx_rate_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Null is unknown; false is a known stock-out. Never conflate the two.
    in_stock: Mapped[bool | None] = mapped_column(nullable=True)
    checked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    product: Mapped[Product] = relationship(back_populates="offers", lazy="raise")
    retailer: Mapped[Retailer] = relationship(lazy="raise")
    sizes: Mapped[list[OfferSize]] = relationship(back_populates="offer", lazy="raise")


class OfferSize(IdMixin, TimestampMixin, Base):
    """One size of an offer and whether it is in stock.

    A row per size rather than an array: availability is queried per size, and
    "unknown" has to be expressible for a single size without erasing the rest.
    """

    __tablename__ = "offer_sizes"
    __table_args__ = (
        UniqueConstraint(
            "offer_id", "size_system", "size_value", name="unique_offer_sizes_offer_id_size"
        ),
    )

    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offers.id", name="fk_offer_sizes_offer_id", ondelete="CASCADE"), nullable=False
    )
    size_system: Mapped[SizeSystem] = mapped_column(
        SAEnum(SizeSystem, name="size_system"), nullable=False
    )
    size_value: Mapped[str] = mapped_column(String(32), nullable=False)
    in_stock: Mapped[bool | None] = mapped_column(nullable=True)

    offer: Mapped[Offer] = relationship(back_populates="sizes", lazy="raise")
