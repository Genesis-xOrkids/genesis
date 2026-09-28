"""Shopify Catalog connector.

Shopify is the highest-coverage source for the DTC and Instagram-native brands
the consumer product is built around. Its records arrive as nested product nodes
with variants; this translates them into one canonical product plus one offer
per store, with the variants collapsed into sizes.

The nesting is where the shapes differ most from ours, and it is contained here:
nothing downstream knows Shopify has variants.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from api.genesis_api.models.enums import SizeSystem
from intelligence.catalog import vocabulary
from intelligence.catalog.color import ColorError, family_for_hex, family_for_name, parse_hex
from intelligence.catalog.money import (
    CurrencyError,
    FxRates,
    to_minor_units,
    to_usd_cents_as_of,
)
from intelligence.catalog.normalized import (
    NormalizationResult,
    NormalizedImage,
    NormalizedOffer,
    NormalizedProduct,
    NormalizedSize,
    SourceRecord,
)
from intelligence.catalog.sizes import parse_size

SOURCE = "shopify"


class ShopifyConnector:
    """Translates Shopify Catalog product nodes."""

    def __init__(self, *, rates: FxRates, store_name: str) -> None:
        self._rates = rates
        self._store_name = store_name

    @property
    def source(self) -> str:
        return SOURCE

    def normalize(self, records: Iterable[Any]) -> NormalizationResult:
        result = NormalizationResult()
        for record in records:
            source_id = str(record.get("id") or "")
            raw = SourceRecord(
                source=SOURCE, source_id=source_id, payload=json.dumps(record, default=str)
            )
            if not source_id:
                result.record_failure(raw, "identify", "record has no id")
                continue
            rejected = vocabulary.not_apparel(str(record.get("title") or ""))
            if rejected is not None:
                result.record_failure(raw, "filter", str(rejected))
                continue
            try:
                product, offer = self._one(record, source_id)
            except (CurrencyError, ColorError, ValueError, KeyError, TypeError) as exc:
                result.record_failure(raw, "normalize", f"{type(exc).__name__}: {exc}")
                continue
            result.products.append(product)
            if offer is not None:
                result.offers.append(offer)
        return result

    def _one(
        self, record: dict[str, Any], source_id: str
    ) -> tuple[NormalizedProduct, NormalizedOffer | None]:
        title = str(record.get("title") or "").strip()
        if not title:
            raise ValueError("product has no title")

        description = record.get("descriptionHtml") or record.get("description")
        product_type = record.get("productType")
        tags = " ".join(record.get("tags") or [])
        # The garment's own name leads; a merchandising department is a shelf
        # rather than a description of what the thing is.
        texts = (title, product_type, tags, description)

        color_hex, color_family = self._color(record)

        product = NormalizedProduct(
            source=SOURCE,
            source_id=source_id,
            title=title,
            brand_name=(record.get("vendor") or None),
            description=description,
            gender=vocabulary.gender_for(tags, product_type, title),
            **vocabulary.attributes_for(*texts),
            color_hex=color_hex,
            color_family=color_family,
            images=tuple(
                NormalizedImage(
                    source_url=image["url"],
                    position=index,
                    width_px=image.get("width"),
                    height_px=image.get("height"),
                )
                for index, image in enumerate(record.get("images") or [])
                if image.get("url")
            ),
        )
        return product, self._offer(record, source_id)

    def _color(self, record: dict[str, Any]) -> tuple[str | None, Any]:
        """Hex is the fact; family is derived from it, or from a name when the
        family is one hex cannot express."""
        raw_hex = record.get("colorHex")
        name = record.get("color")
        color_hex = parse_hex(raw_hex) if raw_hex else None
        named = family_for_name(name) if name else None
        if named is not None:
            return color_hex, named
        return color_hex, family_for_hex(color_hex) if color_hex else None

    def _offer(self, record: dict[str, Any], source_id: str) -> NormalizedOffer | None:
        variants = record.get("variants") or []
        if not variants:
            return None

        currency = str(record.get("currencyCode") or "USD").upper()
        cheapest = min(variants, key=lambda v: float(v.get("price", "inf")))
        minor = to_minor_units(str(cheapest["price"]), currency)

        sale_minor: int | None = None
        compare_at = cheapest.get("compareAtPrice")
        if compare_at:
            # Shopify's compareAtPrice is the pre-markdown price, so the listed
            # price is the sale price when one is present. Recording it the other
            # way round would invert every discount in the catalog.
            sale_minor = minor
            minor = to_minor_units(str(compare_at), currency)

        usd_cents, fx_at = to_usd_cents_as_of(minor, currency, self._rates)

        sizes: list[NormalizedSize] = []
        for variant in variants:
            label = variant.get("title") or variant.get("option1")
            if not label or str(label).lower() == "default title":
                continue
            parsed = parse_size(str(label), declared_system=self._declared_system(record))
            if parsed is None:
                continue
            available = variant.get("availableForSale")
            sizes.append(
                NormalizedSize(
                    system=parsed.system,
                    value=parsed.value,
                    in_stock=None if available is None else bool(available),
                )
            )

        any_available = [v.get("availableForSale") for v in variants]
        in_stock = (
            None if all(a is None for a in any_available) else any(bool(a) for a in any_available)
        )

        return NormalizedOffer(
            source=SOURCE,
            source_id=f"{source_id}@{self._store_name}",
            product_source_id=source_id,
            retailer_name=self._store_name,
            url=str(record.get("onlineStoreUrl") or record.get("url") or ""),
            price_amount_minor=minor,
            currency=currency,
            sale_price_amount_minor=sale_minor,
            price_usd_cents=usd_cents,
            fx_rate_at=fx_at,
            in_stock=in_stock,
            sizes=tuple(sizes),
        )

    def _declared_system(self, record: dict[str, Any]) -> SizeSystem | None:
        declared = record.get("sizeSystem")
        if not declared:
            return None
        try:
            return SizeSystem(str(declared).lower())
        except ValueError:
            return None
