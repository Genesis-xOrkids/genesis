"""Every model, imported once.

Alembic autogenerate and the GraphQL type builder both walk ``Base.metadata``,
so a model that is never imported here is invisible to both. Importing a new
module is part of adding a model, not an afterthought.
"""

from api.genesis_api.models.base import Base, IdMixin, TimestampMixin
from api.genesis_api.models.brand import BrandCode, BrandTenant
from api.genesis_api.models.catalog import (
    FASHION_EMBEDDING_DIMS,
    Offer,
    OfferSize,
    Product,
    ProductAttribute,
    ProductImage,
    ProductMaterial,
)
from api.genesis_api.models.taxonomy import Brand, Retailer, TaxonomyValue
from api.genesis_api.models.user import (
    StyleProfile,
    StyleProfileAesthetic,
    StyleProfileBrand,
    StyleProfileBudget,
    StyleProfileColor,
    StyleProfileSilhouette,
    StyleProfileSize,
    User,
    UserConsent,
)

__all__ = [
    "FASHION_EMBEDDING_DIMS",
    "Base",
    "Brand",
    "BrandCode",
    "BrandTenant",
    "IdMixin",
    "Offer",
    "OfferSize",
    "Product",
    "ProductAttribute",
    "ProductImage",
    "ProductMaterial",
    "Retailer",
    "StyleProfile",
    "StyleProfileAesthetic",
    "StyleProfileBrand",
    "StyleProfileBudget",
    "StyleProfileColor",
    "StyleProfileSilhouette",
    "StyleProfileSize",
    "TaxonomyValue",
    "TimestampMixin",
    "User",
    "UserConsent",
]
