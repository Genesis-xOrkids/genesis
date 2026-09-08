"""Shopify public storefront connector.

Reads the ``/products.json`` document Shopify publishes on every storefront: a
public, unauthenticated, structured feed intended for machine consumption. It is
the coverage supplement for brands we have no partner relationship with, not the
primary path - it carries no affiliate link, so it earns nothing on its own.

Where a storefront advertises UCP (see :mod:`intelligence.catalog.ucp`), prefer
it. Shopify's own agent instructions say so, and a sanctioned protocol does not
change shape underneath us the way a page can.

The payload is snake_case and shaped nothing like the partner Catalog API, so
this is its own connector rather than a configuration of that one. Two details
drive most of the translation: variants carry their options positionally
(``option1``..``option3``, resolved through the product's ``options`` list), and
the document carries no currency at all - that comes from the store's
``/meta.json`` and is configuration here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from api.genesis_api.models.enums import ColorFamily, SizeSystem
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

_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")

# Option names that identify the size and color axes. Merchants name these
# themselves, so the match is on a small set of conventions rather than position.
_SIZE_OPTION_NAMES = {"size", "sizes", "shoe size", "waist", "length"}
_COLOR_OPTION_NAMES = {"color", "colour", "shade", "colorway"}

# Storefronts sell warranties, gift cards, and shipping protection through the
# same catalog. They are real products and none of them are clothing, so they are
# filtered rather than ingested and later explained away.
_NON_GARMENT_TERMS = {
    "gift card",
    "e-gift",
    "egift",
    "warranty",
    "protection",
    "insurance",
    "shipping",
    "donation",
    "sample",
    "swatch",
    "returns coverage",
    "package protection",
    "carbon offset",
    "extended care",
}


# A storefront states its own country in /meta.json. That stated fact gives a
# default size system for the bare numeric labels these feeds are full of
# ("00", "0", "2"), which would otherwise be dropped as ambiguous. It is a
# per-store default, not a per-product guess: if it is wrong it is wrong
# consistently and visibly, and the operator overrides it on the profile.
_COUNTRY_SIZE_SYSTEMS: dict[str, SizeSystem] = {
    "US": SizeSystem.us,
    "CA": SizeSystem.us,
    "GB": SizeSystem.uk,
    "AU": SizeSystem.uk,
    "FR": SizeSystem.fr,
    "IT": SizeSystem.it,
    "JP": SizeSystem.jp,
    "DE": SizeSystem.eu,
    "ES": SizeSystem.eu,
    "NL": SizeSystem.eu,
    "SE": SizeSystem.eu,
    "DK": SizeSystem.eu,
}


@dataclass(frozen=True)
class StorefrontProfile:
    """What we know about one storefront before reading its products.

    ``currency`` is required because ``/products.json`` omits it entirely; a
    price without its currency is not a fact. It comes from the store's
    ``/meta.json``, which is why :func:`fetch_storefront_profile` exists rather
    than leaving callers to assume USD.
    """

    domain: str
    retailer_name: str
    currency: str
    brand_name: str | None = None
    # The system bare numeric sizes are quoted in. Defaulted from the store's
    # own stated country and overridable; never inferred per product.
    size_system: SizeSystem | None = None


def fetch_storefront_profile(fetcher: Any, domain: str) -> StorefrontProfile:
    """Read a storefront's own metadata to learn its name and currency."""
    meta = fetcher.get_json(f"https://{domain}/meta.json")
    name = meta.get("name") or domain
    currency = meta.get("currency")
    if not currency:
        raise ValueError(
            f"{domain}/meta.json states no currency; supply one explicitly rather "
            "than defaulting, because a price without a currency is not a fact"
        )
    country = str(meta.get("country") or "").upper()
    return StorefrontProfile(
        domain=domain,
        retailer_name=name,
        currency=currency,
        brand_name=name,
        size_system=_COUNTRY_SIZE_SYSTEMS.get(country),
    )


def strip_html(raw: str | None) -> str | None:
    """Reduce ``body_html`` to text.

    The markup is never useful downstream and description text reaches a model,
    so tags are removed here rather than travelling further as untrusted markup.
    """
    if not raw:
        return None
    text = _WHITESPACE.sub(" ", _HTML_TAG.sub(" ", raw)).strip()
    return text or None


# Merchandisers separate the colourway from the product name with a pipe or a
# spaced dash, and both conventions appear across storefronts.
_TITLE_SEPARATORS = re.compile(r"\s+[|\u2013\u2014-]\s+|\|")
# Parentheticals describe a trim or a sole, not the garment: "Natural Black
# (Dark Grey Sole)" is a black shoe, and matching inside the bracket would make
# it grey.
_PARENTHETICAL = re.compile(r"\([^)]*\)")


def _title_colour_segments(title: str) -> list[str]:
    """Segments of a title that may name the colourway, most likely first.

    Everything after the product name, in order: "Barrel Jean | Washed Black |
    Regular" names the colour in the segment right after the name, with fit
    following it.
    """
    parts = _TITLE_SEPARATORS.split(title)
    return [_PARENTHETICAL.sub(" ", part).strip() for part in parts[1:] if part.strip()]


_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    """A stable id fragment for a colourway name."""
    return _SLUG.sub("-", value.lower()).strip("-") or "default"


def looks_like_a_garment(title: str, product_type: str | None) -> bool:
    haystack = f"{title} {product_type or ''}".lower()
    return not any(term in haystack for term in _NON_GARMENT_TERMS)


class ShopifyPublicConnector:
    """Translates one storefront's public product feed."""

    def __init__(self, *, profile: StorefrontProfile, rates: FxRates) -> None:
        self._profile = profile
        self._rates = rates

    @property
    def source(self) -> str:
        # Scoped to the storefront: the same numeric product id exists on every
        # Shopify store, so a shared source would collide across brands.
        return f"shopify-public:{self._profile.domain}"

    def normalize(self, records: Iterable[Any]) -> NormalizationResult:
        result = NormalizationResult()
        for record in records:
            source_id = str(record.get("id") or "")
            raw = SourceRecord(
                source=self.source, source_id=source_id, payload=json.dumps(record, default=str)
            )
            if not source_id:
                result.record_failure(raw, "identify", "product has no id")
                continue

            title = str(record.get("title") or "").strip()
            if not title:
                result.record_failure(raw, "identify", "product has no title")
                continue
            if not looks_like_a_garment(title, record.get("product_type")):
                result.record_failure(raw, "filter", "not a garment (service or gift SKU)")
                continue

            try:
                pairs = self._colourways(record, source_id, title)
            except (CurrencyError, ColorError, ValueError, KeyError, TypeError) as exc:
                result.record_failure(raw, "normalize", f"{type(exc).__name__}: {exc}")
                continue

            for product, offer in pairs:
                result.products.append(product)
                if offer is not None:
                    result.offers.append(offer)
        return result

    def _colourways(
        self, record: dict[str, Any], source_id: str, title: str
    ) -> list[tuple[NormalizedProduct, NormalizedOffer | None]]:
        """Split one source record into one product per colourway.

        Storefronts model colour two ways. Some publish a separate record per
        colourway, naming it in the title. Others publish one record with colour
        as a variant option, so a single shoe covers a dozen colourways.

        Our model treats a colourway as part of what a product is, so the second
        shape has to be split rather than flattened. Flattening it loses colour
        entirely, and colour is one of the two filters a shopper reaches for
        first. Each split product gets a stable id derived from the source id and
        the colour name, so re-runs update rather than duplicating.
        """
        colour_index = self._option_index(record, _COLOR_OPTION_NAMES)
        colours = self._option_values(record, _COLOR_OPTION_NAMES)

        if colour_index is None or len(colours) <= 1:
            return [self._one(record, source_id, title)]

        pairs: list[tuple[NormalizedProduct, NormalizedOffer | None]] = []
        for colour in colours:
            variants = [
                variant
                for variant in record.get("variants") or []
                if str(variant.get(f"option{colour_index}") or "") == colour
            ]
            if not variants:
                continue
            scoped = {
                **record,
                "variants": variants,
                "images": self._images_for(record, variants),
            }
            pairs.append(
                self._one(
                    scoped,
                    f"{source_id}:{_slug(colour)}",
                    title,
                    colour_override=colour,
                )
            )
        return pairs or [self._one(record, source_id, title)]

    def _images_for(
        self, record: dict[str, Any], variants: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Images belonging to one colourway.

        Shopify links images to variants, so a split product can carry its own
        photographs rather than the whole range's. Where no image declares a
        link, every image is kept: showing the range beats showing nothing.
        """
        images = record.get("images") or []
        wanted = {variant.get("id") for variant in variants if variant.get("id") is not None}
        scoped = [image for image in images if wanted.intersection(image.get("variant_ids") or [])]
        return scoped or images

    def _one(
        self,
        record: dict[str, Any],
        source_id: str,
        title: str,
        *,
        colour_override: str | None = None,
    ) -> tuple[NormalizedProduct, NormalizedOffer | None]:
        description = strip_html(record.get("body_html"))
        product_type = record.get("product_type")
        tags = record.get("tags") or []
        tag_text = " ".join(str(tag) for tag in tags)
        colour = self._option_values(record, _COLOR_OPTION_NAMES)

        # The garment's own name leads. A merchandising department is a shelf
        # rather than a description, and trusting it labelled "Knit Cami Mini
        # Dress" a sweater because the storefront files it under knitwear.
        texts = (title, product_type, tag_text, description)

        colour_hex = parse_hex(str(record["color_hex"])) if record.get("color_hex") else None
        family = (
            family_for_name(colour_override)
            if colour_override
            else self._colour_family(title, tags, colour, colour_hex)
        )

        product = NormalizedProduct(
            source=self.source,
            source_id=source_id,
            title=title,
            brand_name=record.get("vendor") or self._profile.brand_name,
            description=description,
            gender=vocabulary.gender_for(tag_text, product_type, title),
            **vocabulary.attributes_for(*texts),
            color_hex=colour_hex,
            color_family=family,
            images=tuple(
                NormalizedImage(
                    source_url=image["src"],
                    position=int(image.get("position", index + 1)) - 1,
                    width_px=image.get("width"),
                    height_px=image.get("height"),
                )
                for index, image in enumerate(record.get("images") or [])
                if image.get("src")
            ),
        )
        return product, self._offer(record, source_id)

    def _colour_family(
        self,
        title: str,
        tags: list[Any],
        colour_options: list[str],
        colour_hex: str | None,
    ) -> ColorFamily | None:
        """Work out the colour from whatever the storefront actually states.

        This feed has no colour field. The colour lives in a variant option, in
        the back half of the title, or in the tags. Sources are tried in order of
        precision rather than convenience: the colourway name a merchandiser
        wrote is more specific than the bucket they filed it under. A product
        named "Deep Navy" and tagged "Blue" is navy, and for a stylist that
        distinction is the whole point of storing colour.

        A product offering several colourways is left with no colour rather than
        assigned one of them. Our model treats a colourway as part of what a
        product is, so the honest representation is to split it into separate
        products; asserting the first would quietly mislabel the rest.
        """
        if len(colour_options) > 1:
            return None
        if len(colour_options) == 1:
            named = family_for_name(colour_options[0])
            if named is not None:
                return named

        for segment in _title_colour_segments(title):
            named = family_for_name(segment)
            if named is not None:
                return named

        for tag in tags:
            named = family_for_name(str(tag))
            if named is not None:
                return named

        if colour_hex:
            return family_for_hex(colour_hex)
        return None

    def _option_index(self, record: dict[str, Any], names: set[str]) -> int | None:
        for option in record.get("options") or []:
            if str(option.get("name", "")).strip().lower() in names:
                position = int(option.get("position", 0))
                if 1 <= position <= 3:
                    return position
        return None

    def _size_option_index(self, record: dict[str, Any]) -> int | None:
        """Which of ``option1``..``option3`` holds the size, by option name."""
        for option in record.get("options") or []:
            if str(option.get("name", "")).strip().lower() in _SIZE_OPTION_NAMES:
                position = int(option.get("position", 0))
                if 1 <= position <= 3:
                    return position
        return None

    def _option_values(self, record: dict[str, Any], names: set[str]) -> list[str]:
        for option in record.get("options") or []:
            if str(option.get("name", "")).strip().lower() in names:
                return [str(value) for value in option.get("values") or []]
        return []

    def _offer(self, record: dict[str, Any], source_id: str) -> NormalizedOffer | None:
        variants = record.get("variants") or []
        if not variants:
            return None

        # Service line items are not shippable; a product whose variants all
        # decline shipping is not clothing however its title reads.
        if all(variant.get("requires_shipping") is False for variant in variants):
            raise ValueError("no shippable variant")

        currency = self._profile.currency
        priced = [v for v in variants if v.get("price") not in (None, "")]
        if not priced:
            raise ValueError("no variant carries a price")
        cheapest = min(priced, key=lambda v: float(v["price"]))
        minor = to_minor_units(str(cheapest["price"]), currency)

        sale_minor: int | None = None
        compare_at = cheapest.get("compare_at_price")
        if compare_at:
            was = to_minor_units(str(compare_at), currency)
            # compare_at_price is the pre-markdown price, so the listed price is
            # the sale price when it is genuinely lower. Merchants leave stale
            # compare_at values behind constantly, and treating one as a markdown
            # would badge an undiscounted item.
            if was > minor:
                sale_minor, minor = minor, was

        usd_cents, fx_at = to_usd_cents_as_of(minor, currency, self._rates)

        size_index = self._size_option_index(record)
        sizes: list[NormalizedSize] = []
        for variant in variants:
            label = variant.get(f"option{size_index}") if size_index else variant.get("title")
            if not label or str(label).strip().lower() == "default title":
                continue
            parsed = parse_size(str(label), declared_system=self._profile.size_system)
            if parsed is None:
                continue
            available = variant.get("available")
            sizes.append(
                NormalizedSize(
                    system=parsed.system,
                    value=parsed.value,
                    in_stock=None if available is None else bool(available),
                )
            )

        flags = [variant.get("available") for variant in variants]
        in_stock = None if all(flag is None for flag in flags) else any(bool(f) for f in flags)

        handle = record.get("handle")
        return NormalizedOffer(
            source=self.source,
            source_id=source_id,
            product_source_id=source_id,
            retailer_name=self._profile.retailer_name,
            url=f"https://{self._profile.domain}/products/{handle}" if handle else "",
            affiliate_url=None,
            price_amount_minor=minor,
            currency=currency,
            sale_price_amount_minor=sale_minor,
            price_usd_cents=usd_cents,
            fx_rate_at=fx_at,
            in_stock=in_stock,
            sizes=tuple(sizes),
        )


def iter_storefront_products(
    fetcher: Any, profile: StorefrontProfile, *, page_size: int = 250, max_pages: int = 40
) -> Iterable[dict[str, Any]]:
    """Page through a storefront's public product feed.

    ``max_pages`` is a guard, not a tuning knob: a paginated endpoint that never
    returns an empty page would otherwise loop forever against someone's server.
    """
    for page in range(1, max_pages + 1):
        payload = fetcher.get_json(
            f"https://{profile.domain}/products.json?limit={page_size}&page={page}"
        )
        products = payload.get("products") or []
        if not products:
            return
        yield from products
        if len(products) < page_size:
            return
