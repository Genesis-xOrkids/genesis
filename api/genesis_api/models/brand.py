"""Brand tenants: the enterprise side of the platform.

A tenant is the isolation boundary. Per-tenant KMS keys, vector indexes, and
agent memory stores all key off ``BrandTenant.id``, and every tenant-scoped
table carries ``tenant_id`` so row-level security has one column to enforce.
"""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.genesis_api.models.base import Base, IdMixin, TimestampMixin
from api.genesis_api.models.enums import Provenance
from api.genesis_api.models.taxonomy import Brand


class BrandTenant(IdMixin, TimestampMixin, Base):
    """An enterprise customer of the Studio.

    Distinct from ``Brand``: a Brand is a label the catalog knows about, a
    BrandTenant is a paying organization with users and data. The optional
    ``brand_id`` links a tenant to its own catalog presence when we carry it,
    which is what lets the Studio compare a tenant against its own market.
    """

    __tablename__ = "brand_tenants"
    __table_args__ = (
        UniqueConstraint("slug", name="unique_brand_tenants_slug"),
        Index("ix_brand_tenants_brand_id", "brand_id"),
    )

    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id", name="fk_brand_tenants_brand_id"), nullable=True
    )
    # The tenant's own KMS key. Null means the tenant has not been provisioned
    # yet, which blocks writing any tenant document.
    kms_key_arn: Mapped[str | None] = mapped_column(Text, nullable=True)

    brand: Mapped[Brand | None] = relationship(lazy="raise")
    codes: Mapped[list[BrandCode]] = relationship(back_populates="tenant", lazy="raise")


class BrandCode(IdMixin, TimestampMixin, Base):
    """One rule of a tenant's design language, with the evidence behind it.

    Codes are extracted from the tenant's own lookbooks and line sheets, then
    corrected by their stylists. Both land in the same rows, told apart by
    ``provenance``. ``weight`` is how central the code is, not how confident we
    are, so a stylist can promote a code the extraction found weakly.
    """

    __tablename__ = "brand_codes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "kind", "value", name="unique_brand_codes_tenant_kind_value"),
        Index("ix_brand_codes_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("brand_tenants.id", name="fk_brand_codes_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    weight: Mapped[float | None] = mapped_column(nullable=True)
    provenance: Mapped[Provenance] = mapped_column(
        SAEnum(Provenance, name="provenance"), nullable=False
    )

    tenant: Mapped[BrandTenant] = relationship(back_populates="codes", lazy="raise")
