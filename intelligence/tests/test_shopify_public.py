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


# --- sizes from option structure -------------------------------------------
# Each record is trimmed from a live /products.json response read on 2026-09-27,
# keeping the option names and variant shapes the size path reads.


def _variant(variant_id: int, title: str, *options: str, available: bool | None) -> dict[str, Any]:
    variant: dict[str, Any] = {
        "id": variant_id,
        "title": title,
        "price": "98.00",
        "available": available,
        "requires_shipping": True,
    }
    for position, value in enumerate(options, start=1):
        variant[f"option{position}"] = value
    return variant


def _sizes(record: dict[str, Any]) -> dict[tuple[SizeSystem, str], bool | None]:
    offer = _connector().normalize([record]).offers[0]
    keys = {(size.system, size.value) for size in offer.sizes}
    assert len(keys) == len(offer.sizes), "one row per size"
    return {(size.system, size.value): size.in_stock for size in offer.sizes}


def test_a_length_option_is_the_inseam_not_the_size() -> None:
    """Girlfriend Collective lists Length before Size. Taking the first match as
    the size read '28" Inseam' as one and left every legging unsized."""
    record = {
        "id": 7753726820415,
        "title": "Redwoods Compressive Moto Pocket Legging",
        "handle": "redwoods-compressive-moto-pocket-legging",
        "product_type": "Compressive Moto Pocket Legging",
        "options": [
            {"name": "Length", "position": 1, "values": ['23.75" Inseam', '28" Inseam']},
            {"name": "Size", "position": 2, "values": ["M", "6XL"]},
        ],
        "variants": [
            _variant(1, '23.75" Inseam / M', '23.75" Inseam', "M", available=False),
            _variant(2, '23.75" Inseam / 6XL', '23.75" Inseam', "6XL", available=False),
            _variant(3, '28" Inseam / M', '28" Inseam', "M", available=True),
            _variant(4, '28" Inseam / 6XL', '28" Inseam', "6XL", available=False),
        ],
    }
    assert _sizes(record) == {
        (SizeSystem.alpha, "M"): True,
        (SizeSystem.alpha, "6XL"): False,
    }


def test_waist_and_length_options_are_one_waist_inseam_size() -> None:
    """Everlane's jeans carry the waist and the inseam as two options. Read alone,
    the waist became US 29, which no US size chart means by it."""
    record = {
        "id": 8057092603990,
        "title": "Classic Straight-Fit Jean",
        "handle": "m-btm-dnm-auth-strt-brn-men-s-core-size-range",
        "product_type": "Denim",
        "options": [
            {"name": "Waist", "position": 1, "values": ["29", "30"]},
            {"name": "Length", "position": 2, "values": ["32", "30"]},
        ],
        "variants": [
            _variant(45775398469718, "29 / 32", "29", "32", available=False),
            _variant(45775398502486, "29 / 30", "29", "30", available=True),
            _variant(45775398535254, "30 / 30", "30", "30", available=None),
        ],
    }
    assert _sizes(record) == {
        (SizeSystem.waist_inseam, "29x32"): False,
        (SizeSystem.waist_inseam, "29x30"): True,
        (SizeSystem.waist_inseam, "30x30"): None,
    }


def test_a_size_and_length_pair_survives_the_colourway_split() -> None:
    """Cozy Earth names the waist "Size" and puts colour first."""
    record = {
        "id": 8076268929204,
        "title": "Men's Everywhere Pant Relaxed Fit",
        "handle": "mens-everywhere-pant-relaxed-fit",
        "product_type": "",
        "options": [
            {"name": "Color", "position": 1, "values": ["Graphite", "Jet Black"]},
            {"name": "Size", "position": 2, "values": ["30"]},
            {"name": "Length", "position": 3, "values": ["32", "30"]},
        ],
        "variants": [
            _variant(1, "Graphite / 30 / 32", "Graphite", "30", "32", available=True),
            _variant(2, "Graphite / 30 / 30", "Graphite", "30", "30", available=True),
            _variant(3, "Jet Black / 30 / 32", "Jet Black", "30", "32", available=True),
        ],
    }
    offers = _connector().normalize([record]).offers
    assert {offer.source_id: {size.value for size in offer.sizes} for offer in offers} == {
        "8076268929204:graphite": {"30x32", "30x30"},
        "8076268929204:jet-black": {"30x32"},
    }


def test_a_length_that_is_not_a_number_leaves_the_size_to_stand_alone() -> None:
    """Alo's 'Regular 30"' names a cut, not an inseam that makes a waist-inseam
    size, and the size is a letter anyway."""
    record = {
        "id": 7569582719156,
        "title": "High-Waist Pursuit Trouser (Regular) - Gravel",
        "handle": "w51436r-high-waist-pursuit-trouser-regular-gravel",
        "product_type": "Women:Bottoms:Pants",
        "options": [
            {"name": "Color", "position": 1, "values": ["Gravel"]},
            {"name": "Size", "position": 2, "values": ["XS", "L"]},
            {"name": "Length", "position": 3, "values": ['Regular 30"']},
        ],
        "variants": [
            _variant(
                1, 'Gravel / XS / Regular 30"', "Gravel", "XS", 'Regular 30"', available=False
            ),
            _variant(2, 'Gravel / L / Regular 30"', "Gravel", "L", 'Regular 30"', available=True),
        ],
    }
    assert _sizes(record) == {(SizeSystem.alpha, "XS"): False, (SizeSystem.alpha, "L"): True}


def test_a_size_is_of_unknown_stock_when_any_variant_carrying_it_is() -> None:
    """Known sold out needs every variant of the size to say so."""
    record = {
        "id": 900,
        "title": "Relaxed Pant",
        "handle": "relaxed-pant",
        "product_type": "Pants",
        "options": [
            {"name": "Size", "position": 1, "values": ["M"]},
            {"name": "Length", "position": 2, "values": ["Short", "Regular"]},
        ],
        "variants": [
            _variant(1, "M / Short", "M", "Short", available=False),
            _variant(2, "M / Regular", "M", "Regular", available=None),
        ],
    }
    assert _sizes(record) == {(SizeSystem.alpha, "M"): None}


def test_a_single_default_title_variant_states_no_size() -> None:
    """ "Default Title" says the listing has no options, not that the garment is
    one size. This live Colorful Standard 3-pack is filed under a product type
    ending "/M", so it has a size; the feed just does not state it here."""
    record = {
        "id": 903,
        "title": "Classic Organic Sock - Mixed 03 (3-Pack)",
        "handle": "classic-organic-sock-mixed-03-3-pack",
        "product_type": "CS6001/Classic Organic Sock 3-Pack/M",
        "options": [{"name": "Title", "position": 1, "values": ["Default Title"]}],
        "variants": [_variant(1, "Default Title", "Default Title", available=True)],
    }
    assert _sizes(record) == {}


def test_default_title_on_one_of_several_variants_says_nothing_about_size() -> None:
    record = {
        "id": 904,
        "title": "Cotton Sock",
        "handle": "cotton-sock",
        "product_type": "Socks",
        "options": [{"name": "Title", "position": 1, "values": ["Default Title"]}],
        "variants": [
            _variant(1, "Default Title", "Default Title", available=True),
            _variant(2, "Default Title", "Default Title", available=True),
        ],
    }
    assert _sizes(record) == {}


def test_a_single_variant_named_for_its_colour_stays_unsized() -> None:
    """Rothy's totes are one variant under a Color option. That states one
    colour, not one size, so no size is recorded."""
    record = {
        "id": 7430170050654,
        "title": "The Lightweight Tote - ReVelvet Cat",
        "handle": "the-lightweight-tote-revelvet-cat",
        "product_type": "The Lightweight Tote",
        "options": [{"name": "Color", "position": 1, "values": ["ReVelvet Cat"]}],
        "variants": [_variant(41910710206558, "ReVelvet Cat", "ReVelvet Cat", available=True)],
    }
    assert _sizes(record) == {}


def test_a_letter_size_with_its_chest_measurement_is_the_letter() -> None:
    """Taylor Stitch's shirts, as published."""
    record = {
        "id": 906,
        "title": "The Jack in Navy Oxford",
        "handle": "the-jack-in-navy-oxford",
        "product_type": "Shirts",
        "options": [{"name": "Size", "position": 1, "values": ["XS - 36", "M - 40"]}],
        "variants": [
            _variant(1, "XS - 36", "XS - 36", available=True),
            _variant(2, "M - 40", "M - 40", available=False),
        ],
    }
    assert _sizes(record) == {(SizeSystem.alpha, "XS"): True, (SizeSystem.alpha, "M"): False}


def test_a_girls_size_with_its_numeric_in_brackets_stays_unknown() -> None:
    """Stelle's girls' sizes. The bracket is the size in a system the label does
    not name, and the letter alone would read as an adult XS in every search."""
    record = {
        "id": 905,
        "title": "Girls Everyday Legging",
        "handle": "girls-everyday-legging",
        "product_type": "Girls Bottoms",
        "options": [
            {"name": "Color", "position": 1, "values": ["Black"]},
            {"name": "Size", "position": 2, "values": ["XS (4/5)", "M (8/9)"]},
        ],
        "variants": [
            _variant(1, "Black / XS (4/5)", "Black", "XS (4/5)", available=True),
            _variant(2, "Black / M (8/9)", "Black", "M (8/9)", available=False),
        ],
    }
    assert _sizes(record) == {}


def test_a_waist_alone_is_not_read_in_the_stores_system() -> None:
    """A waist of 30 is not a US 30, and no system in the enum holds a waist
    without its inseam."""
    record = {
        "id": 907,
        "title": "Pleated Trouser",
        "handle": "pleated-trouser",
        "product_type": "Pants",
        "options": [{"name": "Waist", "position": 1, "values": ["30", "32"]}],
        "variants": [
            _variant(1, "30", "30", available=True),
            _variant(2, "32", "32", available=True),
        ],
    }
    assert _sizes(record) == {}


def test_an_inseam_written_with_an_inch_mark_still_pairs_with_the_waist() -> None:
    record = {
        "id": 908,
        "title": "Slim Chino",
        "handle": "slim-chino",
        "product_type": "Pants",
        "options": [
            {"name": "Size", "position": 1, "values": ["30"]},
            {"name": "Length", "position": 2, "values": ['32"']},
        ],
        "variants": [_variant(1, '30 / 32"', "30", '32"', available=True)],
    }
    assert _sizes(record) == {(SizeSystem.waist_inseam, "30x32"): True}


def test_a_numeric_size_beside_a_cut_keeps_the_stores_system() -> None:
    """A women's 8 in a Short length is a US 8; only a numeric inseam makes the
    number a waist."""
    record = {
        "id": 909,
        "title": "Wide Leg Pant",
        "handle": "wide-leg-pant",
        "product_type": "Pants",
        "options": [
            {"name": "Size", "position": 1, "values": ["8"]},
            {"name": "Length", "position": 2, "values": ["Short"]},
        ],
        "variants": [_variant(1, "8 / Short", "8", "Short", available=True)],
    }
    assert _sizes(record) == {(SizeSystem.us, "8"): True}


@pytest.mark.parametrize(
    ("option_name", "values"),
    [
        # Stone and Strand's monogram initials, which main's title fallback read
        # as S, M and L.
        ("Initial", ["S", "M", "L"]),
        # A product whose only option is the inseam: the number is not a size.
        ("Length", ["30", "32"]),
        ("Style", ["Small", "Large"]),
        ("Pack", ["One", "Two"]),
    ],
)
def test_only_an_option_named_for_the_size_is_read(option_name: str, values: list[str]) -> None:
    record = {
        "id": 910,
        "title": "Charm Necklace",
        "handle": "charm-necklace",
        "product_type": "Accessories",
        "options": [{"name": option_name, "position": 1, "values": values}],
        "variants": [
            _variant(index, value, value, available=True) for index, value in enumerate(values)
        ],
    }
    assert _sizes(record) == {}


def test_a_garments_own_size_option_is_read_but_a_bundles_are_not() -> None:
    """Colorful Standard names a single garment's option "<name> (Size)", and a
    bundle carries one such option per garment, none of them the bundle's."""
    single = {
        "id": 911,
        "title": "Oversized Organic T-Shirt - Navy Blue",
        "handle": "oversized-organic-t-shirt-navy-blue",
        "product_type": "T-Shirt",
        "options": [
            {"name": "Oversized Organic T-Shirt - Navy Blue (Size)", "position": 1, "values": ["M"]}
        ],
        "variants": [_variant(1, "M", "M", available=True)],
    }
    bundle = {
        "id": 912,
        "title": "Classic Organic Bundle",
        "handle": "classic-organic-bundle",
        "product_type": "T-Shirt",
        "options": [
            {"name": "Classic Organic Tee - Navy Blue (Size)", "position": 1, "values": ["M"]},
            {"name": "Classic Organic Crew - Navy Blue (Size)", "position": 2, "values": ["L"]},
        ],
        "variants": [_variant(1, "M / L", "M", "L", available=True)],
    }
    assert _sizes(single) == {(SizeSystem.alpha, "M"): True}
    assert _sizes(bundle) == {}
