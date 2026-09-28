"""The canonical shape a connector produces.

This is the boundary. Everything upstream is source-shaped - Shopify's GraphQL
nodes, an affiliate network's feed columns - and everything downstream is these
dataclasses. The core domain never sees a source's field names, so adding the
next network is a new connector rather than a change to the catalog.

Nothing here is interpretive. A connector reports what its source says, plus the
canonical values derivable from it (a normalized color family, a USD price with
the rate that produced it). Judgments about whether an item is on trend or
flattering are made where they are used.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from api.genesis_api.models.enums import (
    Category,
    ColorFamily,
    Fit,
    GarmentLength,
    Gender,
    Neckline,
    Pattern,
    Rise,
    Silhouette,
    SizeSystem,
    SleeveLength,
    SleeveStyle,
)


@dataclass(frozen=True)
class NormalizedImage:
    source_url: str
    position: int
    width_px: int | None = None
    height_px: int | None = None


@dataclass(frozen=True)
class NormalizedMaterial:
    """One fiber and its share, when the source states one."""

    material: str
    pct: float | None = None


@dataclass(frozen=True)
class NormalizedSize:
    system: SizeSystem
    value: str
    # Null is unknown; False is a known stock-out. A source that lists sizes
    # without availability leaves this null rather than claiming they are in
    # stock.
    in_stock: bool | None = None


@dataclass(frozen=True)
class NormalizedProduct:
    """One purchasable style in one colorway, in canonical terms."""

    source: str
    source_id: str
    title: str
    brand_name: str | None = None
    description: str | None = None
    category: Category | None = None
    gender: Gender | None = None
    silhouette: Silhouette | None = None
    neckline: Neckline | None = None
    sleeve_length: SleeveLength | None = None
    sleeve_style: SleeveStyle | None = None
    garment_length: GarmentLength | None = None
    rise: Rise | None = None
    fit: Fit | None = None
    pattern: Pattern | None = None
    color_hex: str | None = None
    color_family: ColorFamily | None = None
    images: tuple[NormalizedImage, ...] = ()
    materials: tuple[NormalizedMaterial, ...] = ()


@dataclass(frozen=True)
class NormalizedOffer:
    """One product for sale at one retailer.

    ``price_usd_cents`` is present only when a rate was available; when it is
    null the listed amount and currency still stand on their own, which is why
    they are the required fields and the conversion is not.

    ``sizes`` is the offer's complete set of sizes as the source states them
    now, and ingest replaces the stored set with it: a size missing here is
    deleted. It has no default so that no caller can write an offer without
    deciding what its sizes are; one that knows none passes ``()`` and means it.
    """

    source: str
    source_id: str
    product_source_id: str
    retailer_name: str
    url: str
    price_amount_minor: int
    currency: str
    sizes: tuple[NormalizedSize, ...]
    affiliate_url: str | None = None
    sale_price_amount_minor: int | None = None
    price_usd_cents: int | None = None
    fx_rate_at: datetime.datetime | None = None
    in_stock: bool | None = None


@dataclass(frozen=True)
class SourceRecord:
    """One raw record as the connector received it.

    Carried alongside the normalized output so a failure can be quarantined with
    the bytes that caused it, which is the difference between a fixable report
    and "the feed broke".
    """

    source: str
    source_id: str
    payload: str


@dataclass
class NormalizationResult:
    """What one connector run produced, including what it could not read."""

    products: list[NormalizedProduct] = field(default_factory=list)
    offers: list[NormalizedOffer] = field(default_factory=list)
    failures: list[tuple[SourceRecord, str, str]] = field(default_factory=list)

    def record_failure(self, record: SourceRecord, stage: str, error: str) -> None:
        self.failures.append((record, stage, error))
