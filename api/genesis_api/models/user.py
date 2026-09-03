"""Users, their style profile, and the consent that governs their data.

The profile is decomposed into atomic facts across child tables rather than a
document: every preference is independently queryable, and each carries the
provenance of whoever asserted it. A preference stated at intake, inferred from
behavior, and edited by the user all land in the same column, told apart by
``provenance``, never by living in parallel tables.
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
from api.genesis_api.models.enums import (
    BrandRelation,
    Category,
    ColorFamily,
    Provenance,
    Silhouette,
    SizeSystem,
)
from api.genesis_api.models.taxonomy import Brand, TaxonomyValue


class User(IdMixin, TimestampMixin, Base):
    """A person using the consumer product.

    ``tenant_id`` is null for consumers and set for members of a brand tenant;
    one identity table serves both surfaces so authorization has one home.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("auth_subject", name="unique_users_auth_subject"),
        Index("ix_users_tenant_id", "tenant_id"),
    )

    auth_subject: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("brand_tenants.id", name="fk_users_tenant_id"), nullable=True
    )

    consents: Mapped[list[UserConsent]] = relationship(back_populates="user", lazy="raise")
    style_profile: Mapped[StyleProfile | None] = relationship(
        back_populates="user", lazy="raise", uselist=False
    )


class UserConsent(IdMixin, TimestampMixin, Base):
    """A consent decision, as an event.

    Consent is append-only: granting, withdrawing, and re-granting are three
    rows. The current state is the latest row per scope, derived at read time.

    ``__append_only__`` tells the writer to insert rather than upsert. Without it
    the writer would look for a natural key, find none, and refuse the write.
    """

    __append_only__ = True
    __tablename__ = "user_consents"
    __table_args__ = (Index("ix_user_consents_user_id_scope", "user_id", "scope"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_user_consents_user_id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    granted: Mapped[bool] = mapped_column(nullable=False)
    decided_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)

    user: Mapped[User] = relationship(back_populates="consents", lazy="raise")


class StyleProfile(IdMixin, TimestampMixin, Base):
    """The stylist's working understanding of one user.

    Scalars that are genuinely single-valued live here; everything multi-valued
    is a child table. Nothing interpretive is stored: "her archetype is minimalist"
    is a stored assertion with provenance, but "this dress suits her" is derived
    at the point of use.
    """

    __tablename__ = "style_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="unique_style_profiles_user_id"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_style_profiles_user_id", ondelete="CASCADE"), nullable=False
    )
    # Free-text context the user gave in their own words. Kept verbatim: it is
    # the source document the structured facts were extracted from.
    self_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    climate: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    user: Mapped[User] = relationship(back_populates="style_profile", lazy="raise")
    brands: Mapped[list[StyleProfileBrand]] = relationship(
        back_populates="style_profile", lazy="raise"
    )
    aesthetics: Mapped[list[StyleProfileAesthetic]] = relationship(
        back_populates="style_profile", lazy="raise"
    )
    colors: Mapped[list[StyleProfileColor]] = relationship(
        back_populates="style_profile", lazy="raise"
    )
    silhouettes: Mapped[list[StyleProfileSilhouette]] = relationship(
        back_populates="style_profile", lazy="raise"
    )
    budgets: Mapped[list[StyleProfileBudget]] = relationship(
        back_populates="style_profile", lazy="raise"
    )
    sizes: Mapped[list[StyleProfileSize]] = relationship(
        back_populates="style_profile", lazy="raise"
    )


class StyleProfileBrand(IdMixin, TimestampMixin, Base):
    """How a user relates to one brand: shops it, aspires to it, or avoids it."""

    __tablename__ = "style_profile_brands"
    __table_args__ = (
        UniqueConstraint(
            "style_profile_id",
            "brand_id",
            "relation",
            name="unique_style_profile_brands_profile_brand_relation",
        ),
    )

    style_profile_id: Mapped[int] = mapped_column(
        ForeignKey(
            "style_profiles.id", name="fk_style_profile_brands_style_profile_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", name="fk_style_profile_brands_brand_id"), nullable=False
    )
    relation: Mapped[BrandRelation] = mapped_column(
        SAEnum(BrandRelation, name="brand_relation"), nullable=False
    )
    provenance: Mapped[Provenance] = mapped_column(
        SAEnum(Provenance, name="provenance"), nullable=False
    )

    style_profile: Mapped[StyleProfile] = relationship(back_populates="brands", lazy="raise")
    brand: Mapped[Brand] = relationship(lazy="raise")


class StyleProfileAesthetic(IdMixin, TimestampMixin, Base):
    """An aesthetic the user reads as theirs, with how strongly it applies.

    Aesthetics are a versioned open vocabulary, so this points at a taxonomy row
    rather than an enum: "office siren" can arrive without a migration.
    """

    __tablename__ = "style_profile_aesthetics"
    __table_args__ = (
        UniqueConstraint(
            "style_profile_id", "value_id", name="unique_style_profile_aesthetics_profile_value"
        ),
        CheckConstraint("affinity >= -1 and affinity <= 1", name="affinity_range"),
    )

    style_profile_id: Mapped[int] = mapped_column(
        ForeignKey(
            "style_profiles.id",
            name="fk_style_profile_aesthetics_style_profile_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    value_id: Mapped[int] = mapped_column(
        ForeignKey("taxonomy_values.id", name="fk_style_profile_aesthetics_value_id"),
        nullable=False,
    )
    # -1 is actively rejected, +1 is core to their taste. Null is unknown, which
    # is why the column is nullable rather than defaulted to 0.
    affinity: Mapped[float | None] = mapped_column(nullable=True)
    provenance: Mapped[Provenance] = mapped_column(
        SAEnum(Provenance, name="provenance"), nullable=False
    )

    style_profile: Mapped[StyleProfile] = relationship(back_populates="aesthetics", lazy="raise")
    value: Mapped[TaxonomyValue] = relationship(lazy="raise")


class StyleProfileColor(IdMixin, TimestampMixin, Base):
    """A color the user wears or won't."""

    __tablename__ = "style_profile_colors"
    __table_args__ = (
        UniqueConstraint(
            "style_profile_id", "color_family", name="unique_style_profile_colors_profile_color"
        ),
        CheckConstraint("affinity >= -1 and affinity <= 1", name="affinity_range"),
    )

    style_profile_id: Mapped[int] = mapped_column(
        ForeignKey(
            "style_profiles.id", name="fk_style_profile_colors_style_profile_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    color_family: Mapped[ColorFamily] = mapped_column(
        SAEnum(ColorFamily, name="color_family"), nullable=False
    )
    affinity: Mapped[float | None] = mapped_column(nullable=True)
    provenance: Mapped[Provenance] = mapped_column(
        SAEnum(Provenance, name="provenance"), nullable=False
    )

    style_profile: Mapped[StyleProfile] = relationship(back_populates="colors", lazy="raise")


class StyleProfileSilhouette(IdMixin, TimestampMixin, Base):
    """A silhouette the user gravitates to or avoids."""

    __tablename__ = "style_profile_silhouettes"
    __table_args__ = (
        UniqueConstraint(
            "style_profile_id",
            "silhouette",
            name="unique_style_profile_silhouettes_profile_silhouette",
        ),
        CheckConstraint("affinity >= -1 and affinity <= 1", name="affinity_range"),
    )

    style_profile_id: Mapped[int] = mapped_column(
        ForeignKey(
            "style_profiles.id",
            name="fk_style_profile_silhouettes_style_profile_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    silhouette: Mapped[Silhouette] = mapped_column(
        SAEnum(Silhouette, name="silhouette"), nullable=False
    )
    affinity: Mapped[float | None] = mapped_column(nullable=True)
    provenance: Mapped[Provenance] = mapped_column(
        SAEnum(Provenance, name="provenance"), nullable=False
    )

    style_profile: Mapped[StyleProfile] = relationship(back_populates="silhouettes", lazy="raise")


class StyleProfileBudget(IdMixin, TimestampMixin, Base):
    """What the user will spend on one category.

    Bounds are stored in USD cents because that is what the catalog compares
    against; the amount the user actually said is preserved in
    ``self_description`` on the profile.
    """

    __tablename__ = "style_profile_budgets"
    __table_args__ = (
        UniqueConstraint(
            "style_profile_id", "category", name="unique_style_profile_budgets_profile_category"
        ),
        CheckConstraint(
            "max_usd_cents is null or min_usd_cents is null or max_usd_cents >= min_usd_cents",
            name="bounds_ordered",
        ),
    )

    style_profile_id: Mapped[int] = mapped_column(
        ForeignKey(
            "style_profiles.id",
            name="fk_style_profile_budgets_style_profile_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    category: Mapped[Category] = mapped_column(SAEnum(Category, name="category"), nullable=False)
    min_usd_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_usd_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provenance: Mapped[Provenance] = mapped_column(
        SAEnum(Provenance, name="provenance"), nullable=False
    )

    style_profile: Mapped[StyleProfile] = relationship(back_populates="budgets", lazy="raise")


class StyleProfileSize(IdMixin, TimestampMixin, Base):
    """The user's size in one category, optionally brand-specific.

    Sizing is not portable across brands, so ``brand_id`` scopes the fact. Null
    brand means "generally", which is a different assertion, not a missing one.
    """

    __tablename__ = "style_profile_sizes"
    __table_args__ = (
        UniqueConstraint(
            "style_profile_id",
            "category",
            "brand_id",
            name="unique_style_profile_sizes_profile_category_brand",
        ),
    )

    style_profile_id: Mapped[int] = mapped_column(
        ForeignKey(
            "style_profiles.id", name="fk_style_profile_sizes_style_profile_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    category: Mapped[Category] = mapped_column(SAEnum(Category, name="category"), nullable=False)
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id", name="fk_style_profile_sizes_brand_id"), nullable=True
    )
    size_system: Mapped[SizeSystem] = mapped_column(
        SAEnum(SizeSystem, name="size_system"), nullable=False
    )
    size_value: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance: Mapped[Provenance] = mapped_column(
        SAEnum(Provenance, name="provenance"), nullable=False
    )

    style_profile: Mapped[StyleProfile] = relationship(back_populates="sizes", lazy="raise")
    brand: Mapped[Brand | None] = relationship(lazy="raise")
