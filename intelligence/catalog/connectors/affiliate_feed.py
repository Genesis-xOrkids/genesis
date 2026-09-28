"""Affiliate network product-feed connector.

Rakuten Advertising, CJ, Awin and Impact all publish flat product feeds with
broadly the same columns under different names. One connector handles them via a
column map, because the difference between these networks is vocabulary, not
structure - and a class per network would be four copies of one translation.

The shape could not be less like Shopify's: flat rows, prices as bare strings,
sizes as a delimited list, one row per product rather than nested variants.
Both land on the same canonical types, which is the point of the boundary.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
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


@dataclass(frozen=True)
class FeedColumns:
    """Which column holds which fact, for one network's feed."""

    product_id: str = "product_id"
    title: str = "product_name"
    description: str = "description"
    brand: str = "brand"
    category: str = "category"
    price: str = "price"
    sale_price: str = "sale_price"
    currency: str = "currency"
    url: str = "product_url"
    affiliate_url: str = "link"
    image_url: str = "image_url"
    color: str = "color"
    sizes: str = "sizes"
    availability: str = "availability"
    size_delimiter: str = ","
    # Feeds often list bare numbers ("24,25,26") whose system only the operator
    # knows. Declaring it here is configuration; inferring it would be a guess
    # that silently mis-sizes a whole retailer.
    declared_size_system: SizeSystem | None = None


# Rakuten Advertising's product feed specification. Other networks differ only in
# these names, which is why they are data rather than a subclass.
RAKUTEN_COLUMNS = FeedColumns(
    product_id="sku",
    title="productname",
    description="description",
    brand="brand",
    category="primarycategory",
    price="price",
    sale_price="saleprice",
    currency="currency",
    url="linkurl",
    affiliate_url="linkurl",
    image_url="imageurl",
    color="color",
    sizes="size",
    availability="instock",
)


RAKUTEN_DENIM_COLUMNS = replace(RAKUTEN_COLUMNS, declared_size_system=SizeSystem.waist_inseam)

_IN_STOCK_TRUE = {"in stock", "instock", "yes", "y", "true", "1", "available"}
_IN_STOCK_FALSE = {"out of stock", "outofstock", "no", "n", "false", "0", "unavailable"}


class AffiliateFeedConnector:
    """Translates one affiliate network's flat product feed."""

    def __init__(
        self,
        *,
        source: str,
        retailer_name: str,
        rates: FxRates,
        columns: FeedColumns | None = None,
    ) -> None:
        self._source = source
        self._retailer_name = retailer_name
        self._rates = rates
        self._columns = columns or FeedColumns()

    @property
    def source(self) -> str:
        return self._source

    def normalize(self, records: Iterable[Mapping[str, Any]]) -> NormalizationResult:
        result = NormalizationResult()
        columns = self._columns
        for row in records:
            source_id = str(row.get(columns.product_id) or "").strip()
            raw = SourceRecord(
                source=self._source, source_id=source_id, payload=json.dumps(dict(row), default=str)
            )
            if not source_id:
                result.record_failure(raw, "identify", f"row has no {columns.product_id}")
                continue
            rejected = vocabulary.not_apparel(str(row.get(columns.title) or ""))
            if rejected is not None:
                result.record_failure(raw, "filter", str(rejected))
                continue
            try:
                product, offer = self._one(row, source_id)
            except (CurrencyError, ColorError, ValueError, KeyError, TypeError) as exc:
                result.record_failure(raw, "normalize", f"{type(exc).__name__}: {exc}")
                continue
            result.products.append(product)
            result.offers.append(offer)
        return result

    def _one(
        self, row: Mapping[str, Any], source_id: str
    ) -> tuple[NormalizedProduct, NormalizedOffer]:
        columns = self._columns
        title = str(row.get(columns.title) or "").strip()
        if not title:
            raise ValueError(f"row {source_id} has no {columns.title}")

        description = _text(row.get(columns.description))
        category_text = _text(row.get(columns.category))
        # The garment's own name leads over the feed's category column, which
        # is a merchandising shelf rather than a description.
        texts = (title, category_text, description)

        color_name = _text(row.get(columns.color))
        color_hex = None
        raw_hex = _text(row.get("color_hex"))
        if raw_hex:
            color_hex = parse_hex(raw_hex)
        family = family_for_name(color_name) if color_name else None
        if family is None and color_hex:
            family = family_for_hex(color_hex)

        image_url = _text(row.get(columns.image_url))
        product = NormalizedProduct(
            source=self._source,
            source_id=source_id,
            title=title,
            brand_name=_text(row.get(columns.brand)),
            description=description,
            gender=vocabulary.gender_for(category_text, title),
            **vocabulary.attributes_for(*texts),
            color_hex=color_hex,
            color_family=family,
            images=((NormalizedImage(source_url=image_url, position=0),) if image_url else ()),
        )

        currency = (_text(row.get(columns.currency)) or "USD").upper()
        price_text = _text(row.get(columns.price))
        if not price_text:
            raise ValueError(f"row {source_id} has no price")
        minor = to_minor_units(_clean_amount(price_text), currency)

        sale_text = _text(row.get(columns.sale_price))
        sale_minor = None
        if sale_text:
            candidate = to_minor_units(_clean_amount(sale_text), currency)
            # Feeds routinely repeat the list price in the sale column. A "sale"
            # equal to or above list is not a markdown, and recording it as one
            # would show a discount badge on every item in the catalog.
            if candidate < minor:
                sale_minor = candidate

        usd_cents, fx_at = to_usd_cents_as_of(minor, currency, self._rates)

        sizes = tuple(
            NormalizedSize(system=parsed.system, value=parsed.value)
            for label in (_text(row.get(columns.sizes)) or "").split(columns.size_delimiter)
            if label.strip()
            and (parsed := parse_size(label.strip(), declared_system=columns.declared_size_system))
            is not None
        )

        offer = NormalizedOffer(
            source=self._source,
            source_id=source_id,
            product_source_id=source_id,
            retailer_name=self._retailer_name,
            url=_text(row.get(columns.url)) or "",
            affiliate_url=_text(row.get(columns.affiliate_url)),
            price_amount_minor=minor,
            currency=currency,
            sale_price_amount_minor=sale_minor,
            price_usd_cents=usd_cents,
            fx_rate_at=fx_at,
            in_stock=_availability(_text(row.get(columns.availability))),
            sizes=sizes,
        )
        return product, offer


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_amount(text: str) -> str:
    """Strip currency symbols and separators a feed may include.

    Both separator conventions appear in the same networks, and they invert each
    other: "1.234,56" and "1,234.56" are the same amount written by a European
    and a US feed. Whichever separator appears last is the decimal point - that
    rule decides both cases without guessing from the locale. Getting this wrong
    is a silent thousandfold price error, not a parse failure.
    """
    cleaned = "".join(char for char in text if char.isdigit() or char in ".,")
    last_comma = cleaned.rfind(",")
    last_dot = cleaned.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        if last_comma > last_dot:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif last_comma >= 0:
        # A lone comma is a decimal point when it separates the final two or
        # fewer digits, and a thousands separator otherwise.
        if len(cleaned) - last_comma - 1 <= 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    if not cleaned or cleaned in {".", ","}:
        raise ValueError(f"no numeric amount in {text!r}")
    return cleaned


def _availability(text: str | None) -> bool | None:
    """Null stays unknown. A feed that omits availability is not asserting a
    stock-out, and treating it as one would hide half the catalog."""
    if text is None:
        return None
    lowered = text.strip().lower()
    if lowered in _IN_STOCK_TRUE:
        return True
    if lowered in _IN_STOCK_FALSE:
        return False
    return None
