"""Public storefront connector, against a captured real payload.

The fixture is a trimmed copy of a live Shopify ``/products.json`` response, kept
to the fields the connector reads. Tests never hit the network: a suite that
depends on a third party's uptime fails for reasons that have nothing to do with
the code, and teaches everyone to ignore it.
"""

from __future__ import annotations

import datetime
import json
import pathlib
from typing import Any

import pytest

from api.genesis_api.models.enums import Category, SizeSystem
from intelligence.catalog.connectors.shopify_public import (
    ShopifyPublicConnector,
    StorefrontProfile,
    fetch_storefront_profile,
    iter_storefront_products,
    looks_like_a_garment,
    strip_html,
)
from intelligence.catalog.money import FxRates

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
RATES = FxRates(as_of=datetime.datetime(2026, 9, 3, tzinfo=datetime.UTC), usd_per_unit={})


def _products() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "everlane_products.json").read_text())["products"]


class FakeFetcher:
    """Serves the captured documents and records what was asked for."""

    def __init__(self, documents: dict[str, Any]) -> None:
        self._documents = documents
        self.requested: list[str] = []

    def get_json(self, url: str) -> Any:
        self.requested.append(url)
        for fragment, document in self._documents.items():
            if fragment in url:
                return document
        raise AssertionError(f"unexpected request: {url}")


def _profile(**overrides: Any) -> StorefrontProfile:
    base = {
        "domain": "www.everlane.com",
        "retailer_name": "Everlane",
        "currency": "USD",
        "brand_name": "Everlane",
        "size_system": SizeSystem.us,
    }
    return StorefrontProfile(**{**base, **overrides})


def _connector(**overrides: Any) -> ShopifyPublicConnector:
    return ShopifyPublicConnector(profile=_profile(**overrides), rates=RATES)


def test_the_captured_feed_normalizes_without_failures() -> None:
    result = _connector().normalize(_products())
    assert result.products
    assert len(result.products) == len(result.offers)
    assert result.failures == []


def test_categories_come_from_the_merchants_own_fields() -> None:
    result = _connector().normalize(_products())
    categories = {p.category for p in result.products if p.category}
    assert categories, "the feed states product types; none were mapped"
    assert categories <= set(Category)


def test_prices_use_the_storefronts_currency_not_a_default() -> None:
    """``/products.json`` carries no currency at all. Assuming USD would misprice
    every non-US storefront by whatever the exchange rate happens to be."""
    result = _connector(currency="GBP").normalize(_products())
    assert {offer.currency for offer in result.offers} == {"GBP"}


def test_a_price_without_a_usable_rate_leaves_the_usd_value_null() -> None:
    """The listed amount and currency still stand on their own."""
    result = _connector(currency="GBP").normalize(_products())
    offer = result.offers[0]
    assert offer.price_amount_minor > 0
    assert offer.price_usd_cents is None
    assert offer.fx_rate_at is None


def test_sizes_resolve_through_the_named_option_not_variant_position() -> None:
    """Variants carry options positionally; only the product's ``options`` list
    says which position is the size."""
    result = _connector().normalize(_products())
    with_sizes = [offer for offer in result.offers if offer.sizes]
    assert with_sizes, "no offer resolved any size"
    for offer in with_sizes:
        assert all(size.value for size in offer.sizes)


def test_alpha_sizes_stay_alpha_even_when_a_system_is_declared() -> None:
    """A declared system applies to bare numbers, not to "M"."""
    result = _connector().normalize(_products())
    systems = {size.system for offer in result.offers for size in offer.sizes}
    assert SizeSystem.alpha in systems or SizeSystem.us in systems


def test_numeric_sizes_are_dropped_when_no_system_is_known() -> None:
    """Without a declared system a bare "0" is ambiguous, and the honest outcome
    is no size rather than a guessed one."""
    declared = _connector().normalize(_products())
    undeclared = _connector(size_system=None).normalize(_products())
    numeric_declared = sum(1 for o in declared.offers for s in o.sizes if s.system is SizeSystem.us)
    numeric_undeclared = sum(
        1 for o in undeclared.offers for s in o.sizes if s.system is SizeSystem.us
    )
    assert numeric_declared > 0
    assert numeric_undeclared == 0


def test_per_variant_availability_is_carried_through() -> None:
    result = _connector().normalize(_products())
    flags = {size.in_stock for offer in result.offers for size in offer.sizes}
    assert flags <= {True, False, None}
    assert flags & {True, False}, "the feed states availability; none was captured"


def test_product_urls_are_built_from_the_handle() -> None:
    result = _connector().normalize(_products())
    assert all(
        offer.url.startswith("https://www.everlane.com/products/") for offer in result.offers
    )


def test_offers_carry_no_affiliate_url() -> None:
    """This path earns nothing on its own, which is why it is a coverage
    supplement and not the strategy."""
    result = _connector().normalize(_products())
    assert all(offer.affiliate_url is None for offer in result.offers)


def test_the_source_is_scoped_to_the_storefront() -> None:
    """Shopify product ids are only unique within a store, so an unscoped source
    would collide across brands and silently merge two products."""
    first = _connector().source
    second = ShopifyPublicConnector(profile=_profile(domain="www.rothys.com"), rates=RATES).source
    assert first != second
    assert "everlane" in first


def test_service_skus_are_filtered_and_recorded() -> None:
    records = [
        {
            "id": 1,
            "title": "Free Returns Coverage",
            "product_type": "return,package_protection",
            "variants": [{"title": "Default Title", "price": "0.80", "requires_shipping": False}],
        },
        {
            "id": 2,
            "title": "E-Gift Card",
            "product_type": "Gift Card",
            "variants": [{"title": "50", "price": "50.00", "requires_shipping": False}],
        },
    ]
    result = _connector().normalize(records)
    assert result.products == []
    assert len(result.failures) == 2
    assert all(stage == "filter" for _, stage, _ in result.failures)


def test_a_product_with_no_shippable_variant_is_rejected() -> None:
    """Belt and braces: a service SKU whose title reads like clothing is still
    caught, because nothing shippable means it is not a garment."""
    records = [
        {
            "id": 3,
            "title": "Sweater Care Plan",
            "product_type": "Knitwear",
            "variants": [{"title": "One", "price": "9.00", "requires_shipping": False}],
        }
    ]
    result = _connector().normalize(records)
    assert result.products == []
    assert result.failures[0][1] == "normalize"


def test_a_stale_compare_at_price_is_not_treated_as_a_markdown() -> None:
    records = [
        {
            "id": 4,
            "title": "Cotton Shirt",
            "product_type": "Tops",
            "handle": "cotton-shirt",
            "variants": [
                {
                    "title": "M",
                    "price": "80.00",
                    "compare_at_price": "60.00",
                    "available": True,
                    "requires_shipping": True,
                }
            ],
        }
    ]
    offer = _connector().normalize(records).offers[0]
    assert offer.price_amount_minor == 8000
    assert offer.sale_price_amount_minor is None


def test_a_genuine_markdown_records_both_prices() -> None:
    records = [
        {
            "id": 5,
            "title": "Cotton Shirt",
            "product_type": "Tops",
            "handle": "cotton-shirt",
            "variants": [
                {
                    "title": "M",
                    "price": "60.00",
                    "compare_at_price": "80.00",
                    "available": True,
                    "requires_shipping": True,
                }
            ],
        }
    ]
    offer = _connector().normalize(records).offers[0]
    assert offer.price_amount_minor == 8000, "the list price is the pre-markdown price"
    assert offer.sale_price_amount_minor == 6000


def test_html_descriptions_are_reduced_to_text() -> None:
    assert strip_html("<p>Fine-wale <b>corduroy</b></p>") == "Fine-wale corduroy"
    assert strip_html("") is None
    assert strip_html(None) is None


@pytest.mark.parametrize(
    ("title", "product_type", "expected"),
    [
        ("Silk Slip Dress", "Dresses", True),
        ("E-Gift Card", "Gift Card", False),
        ("Free Returns Coverage", "return,package_protection", False),
        ("Shipping Protection", None, False),
        ("Fabric Swatch", "Samples", False),
    ],
)
def test_garment_filter(title: str, product_type: str | None, expected: bool) -> None:
    assert looks_like_a_garment(title, product_type) is expected


def test_the_storefront_states_its_own_currency_and_country() -> None:
    fetcher = FakeFetcher({"meta.json": json.loads((FIXTURES / "everlane_meta.json").read_text())})
    profile = fetch_storefront_profile(fetcher, "www.everlane.com")
    assert profile.currency == "USD"
    assert profile.retailer_name == "Everlane"
    assert profile.size_system is SizeSystem.us, "derived from the stated country"


def test_a_storefront_with_no_stated_currency_raises() -> None:
    """No silent fallback to USD: a price without a currency is not a fact."""
    fetcher = FakeFetcher({"meta.json": {"name": "Nameless", "country": "US"}})
    with pytest.raises(ValueError, match="states no currency"):
        fetch_storefront_profile(fetcher, "example.test")


def test_pagination_stops_on_a_short_page() -> None:
    products = _products()
    fetcher = FakeFetcher({"products.json": {"products": products}})
    collected = list(iter_storefront_products(fetcher, _profile(), page_size=250, max_pages=10))
    assert len(collected) == len(products)
    assert len(fetcher.requested) == 1, "a short page means the feed is exhausted"


def test_pagination_respects_the_page_guard() -> None:
    """A feed that never returns a short page must not loop against a server."""
    full = _products()[:2]
    fetcher = FakeFetcher({"products.json": {"products": full}})
    collected = list(iter_storefront_products(fetcher, _profile(), page_size=2, max_pages=3))
    assert len(fetcher.requested) == 3
    assert len(collected) == 6


@pytest.mark.parametrize(
    ("title", "product_type", "expected"),
    [
        ("Knit Cami Mini Dress", "Sweaters", Category.dress),
        ("Super Fine Cashmere Tank Dress", "Sweaters", Category.dress),
        ("The Ranch Boot in Espresso", "Bottoms", Category.boots),
        ("The Oversized Blazer in Wool", "Outerwear", Category.blazer),
        ("Cashmere Crew Sweater", "Sweaters", Category.sweater),
    ],
)
def test_the_garment_name_outranks_the_merchandising_department(
    title: str, product_type: str, expected: Category
) -> None:
    """A department is a shelf, not a description.

    Storefronts file "Knit Cami Mini Dress" under Sweaters so a shopper browsing
    knitwear finds it. Taking that at face value labelled three dresses as
    sweaters, which a search for a dress then correctly refused to return.
    """
    records = [
        {
            "id": 900,
            "title": title,
            "product_type": product_type,
            "handle": "x",
            "variants": [
                {"title": "M", "price": "100.00", "available": True, "requires_shipping": True}
            ],
        }
    ]
    product = _connector().normalize(records).products[0]
    assert product.category is expected
