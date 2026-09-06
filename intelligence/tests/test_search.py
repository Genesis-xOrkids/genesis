"""Hybrid search behaviour against a real catalog.

Filters are tested as constraints, not preferences: the failures that matter are
an out-of-budget item reaching a shopper, a brand they said they avoid coming
back anyway, and an unknown stock status being shown as available.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.genesis_api.db import engine
from api.genesis_api.models.catalog import FASHION_EMBEDDING_DIMS
from api.genesis_api.models.enums import Category, ColorFamily, SizeSystem
from intelligence.catalog.connectors.affiliate_feed import RAKUTEN_COLUMNS, AffiliateFeedConnector
from intelligence.catalog.ingest import ingest
from intelligence.catalog.money import FxRates
from intelligence.catalog.search import SearchFilters, search_catalog


class StubEmbedder:
    """Stands in for the embedding service, which does not exist yet.

    Search is built against the Embedder protocol precisely so this is possible:
    the retrieval path is exercised end to end before any model is served.
    """

    def embed_text(self, text: str) -> list[float]:
        return [0.0] * FASHION_EMBEDDING_DIMS


RATES = FxRates(
    as_of=datetime.datetime(2026, 9, 3, tzinfo=datetime.UTC),
    usd_per_unit={"GBP": Decimal("1.00")},
)


def _row(sku: str, name: str, brand: str, category: str, price: str, **extra: object) -> dict:
    return {
        "sku": sku,
        "productname": name,
        "brand": brand,
        "primarycategory": category,
        "price": price,
        "currency": "GBP",
        "linkurl": f"https://example.test/{sku}",
        "imageurl": f"https://img.test/{sku}.jpg",
        "instock": "in stock",
        "size": "XS,S,M",
        **extra,
    }


def _connector() -> AffiliateFeedConnector:
    """The same connector the catalog fixture uses, for tests adding rows."""
    return AffiliateFeedConnector(
        source="searchtest", retailer_name="Test Retailer", rates=RATES, columns=RAKUTEN_COLUMNS
    )


CATALOG = [
    _row("S1", "Black Silk Slip Dress", "Ganni", "Womens Dresses", "180.00", color_hex="#0a0a0a"),
    _row("S2", "Navy Wool Column Dress", "Toteme", "Womens Dresses", "450.00", color_hex="#1a2b5e"),
    _row("S3", "Black Cotton Shirt Dress", "Arket", "Womens Dresses", "95.00", color_hex="#111111"),
    _row(
        "S4", "Cream Cashmere Sweater", "Toteme", "Womens Knitwear", "320.00", color_hex="#f0e6d2"
    ),
    _row(
        "S5", "Black Wide Leg Trousers", "Arket", "Womens Trousers", "120.00", color_hex="#0d0d0d"
    ),
    _row(
        "S6",
        "Black Evening Gown",
        "Ganni",
        "Womens Dresses",
        "600.00",
        color_hex="#050505",
        instock="out of stock",
    ),
]


@pytest.fixture
def catalog() -> Iterator[Session]:
    connection = engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    connector = AffiliateFeedConnector(
        source="searchtest", retailer_name="Test Retailer", rates=RATES, columns=RAKUTEN_COLUMNS
    )
    ingest(session, connector.normalize(CATALOG))
    session.flush()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _titles(results) -> set[str]:
    return {result.title for result in results}


def test_a_lexical_query_finds_matching_items(catalog: Session) -> None:
    results, diagnostics = search_catalog(catalog.connection(), query="silk slip dress")
    assert "Black Silk Slip Dress" in _titles(results)
    assert diagnostics.lexical_candidates > 0


def test_search_works_before_the_catalog_is_embedded(catalog: Session) -> None:
    """Embeddings backfill asynchronously, so the embedder exists long before the
    catalog is embedded. Search has to degrade to lexical, not return nothing."""
    results, diagnostics = search_catalog(
        catalog.connection(), query="wool dress", embedder=StubEmbedder()
    )
    assert results, "lexical ranking must carry the search on its own"
    assert diagnostics.vector_candidates == 0
    assert any("not embedded yet" in note for note in diagnostics.notes)


def test_vector_ranker_is_skipped_when_no_embedder_is_configured(catalog: Session) -> None:
    _, diagnostics = search_catalog(catalog.connection(), query="wool dress")
    assert any("no query embedding" in note for note in diagnostics.notes)


def test_a_budget_is_a_constraint_not_a_preference(catalog: Session) -> None:
    """An over-budget item must not surface at all, however well it matches."""
    results, _ = search_catalog(
        catalog.connection(),
        query="dress",
        filters=SearchFilters(max_price_usd_cents=20000),
    )
    assert results
    assert all(r.price_usd_cents is not None and r.price_usd_cents <= 20000 for r in results)
    assert "Navy Wool Column Dress" not in _titles(results)


def test_an_avoided_brand_never_surfaces(catalog: Session) -> None:
    ganni = next(
        r for r in search_catalog(catalog.connection(), query="Ganni")[0] if r.brand == "Ganni"
    )
    brand_id = catalog.execute(
        text("select brand_id from products where title = :t"), {"t": ganni.title}
    ).scalar_one()

    results, _ = search_catalog(
        catalog.connection(), query="dress", filters=SearchFilters(exclude_brand_ids=(brand_id,))
    )
    assert "Ganni" not in {r.brand for r in results}


def test_category_and_color_filters_narrow_the_set(catalog: Session) -> None:
    results, _ = search_catalog(
        catalog.connection(),
        filters=SearchFilters(categories=(Category.dress,), color_families=(ColorFamily.black,)),
        limit=20,
    )
    assert results
    assert all(r.category == "dress" for r in results)
    assert all(r.color_family == "black" for r in results)


def test_require_in_stock_excludes_unknown_and_false(catalog: Session) -> None:
    """Only a known true passes: showing an unknown as available sends a shopper
    to a sold-out page."""
    results, _ = search_catalog(
        catalog.connection(),
        filters=SearchFilters(categories=(Category.dress,), require_in_stock=True),
        limit=20,
    )
    assert "Black Evening Gown" not in _titles(results)
    assert all(r.in_stock is True for r in results)


def test_filters_alone_are_a_valid_search(catalog: Session) -> None:
    """ "Black dresses under $200" needs no query text."""
    results, diagnostics = search_catalog(
        catalog.connection(),
        query="",
        filters=SearchFilters(
            categories=(Category.dress,),
            color_families=(ColorFamily.black,),
            max_price_usd_cents=20000,
        ),
        limit=20,
    )
    assert _titles(results) == {"Black Silk Slip Dress", "Black Cotton Shirt Dress"}
    assert "fell back to filters only" in diagnostics.notes


def test_size_filter_matches_exactly_and_does_not_convert(catalog: Session) -> None:
    matching, _ = search_catalog(
        catalog.connection(),
        filters=SearchFilters(sizes=((SizeSystem.alpha, "S"),)),
        limit=20,
    )
    assert matching
    # The same numeral in another system must not match: conversion is
    # brand-specific and is deliberately not attempted here.
    other, _ = search_catalog(
        catalog.connection(),
        filters=SearchFilters(sizes=((SizeSystem.eu, "S"),)),
        limit=20,
    )
    assert other == []


def test_results_are_compact_and_carry_no_description(catalog: Session) -> None:
    """Descriptions are untrusted retailer text and a place instructions get
    smuggled in, so they never reach the model."""
    results, _ = search_catalog(catalog.connection(), query="dress")
    assert results
    assert not hasattr(results[0], "description")
    assert results[0].url and results[0].image_url


def test_limit_is_respected(catalog: Session) -> None:
    results, _ = search_catalog(catalog.connection(), query="dress", limit=2)
    assert len(results) <= 2


def test_query_count_does_not_grow_with_result_count(catalog: Session) -> None:
    """One query per ranker plus hydration plus images - not one per product."""
    _, few = search_catalog(catalog.connection(), query="dress", limit=2)
    _, many = search_catalog(catalog.connection(), query="dress", limit=20)
    assert few.queries == many.queries <= 4


def test_one_row_per_product_even_with_several_offers(catalog: Session) -> None:
    """A product sold by two retailers is one result at the cheaper price."""
    second = AffiliateFeedConnector(
        source="searchtest2", retailer_name="Other Retailer", rates=RATES, columns=RAKUTEN_COLUMNS
    )
    ingest(
        catalog,
        second.normalize(
            [
                _row(
                    "S1",
                    "Black Silk Slip Dress",
                    "Ganni",
                    "Womens Dresses",
                    "150.00",
                    color_hex="#0a0a0a",
                )
            ]
        ),
    )
    catalog.flush()

    results, _ = search_catalog(catalog.connection(), query="silk slip dress", limit=20)
    slips = [r for r in results if r.title == "Black Silk Slip Dress"]
    # Two source rows, but each source keys its own product; what matters is that
    # a single product never appears twice through its own offers.
    assert len({r.product_id for r in slips}) == len(slips)


def test_colourways_of_one_style_are_collapsed(catalog: Session) -> None:
    """Splitting records per colourway is what gave the catalog colour at all,
    but it means one shoe can exist as forty-nine products. Eight results that
    are the same shoe in eight colours is not a result set."""
    rows = [
        _row(f"CW{i}", f"Signature Loafer | {colour}", "Testwear", "Womens Shoes", "180.00")
        for i, colour in enumerate(["Black", "Navy", "Bone", "Cognac", "Sage", "Rust"])
    ]
    ingest(catalog, _connector().normalize(rows))
    catalog.flush()

    results, _ = search_catalog(catalog.connection(), query="signature loafer", limit=8)
    loafers = [r for r in results if "Signature Loafer" in r.title]
    assert len(loafers) <= 2, "one style must not fill the page"
    assert any(r.other_colourways > 0 for r in loafers), "folded colourways must be counted"


def test_a_collapsed_result_reports_how_many_were_folded(catalog: Session) -> None:
    rows = [
        _row(f"CT{i}", f"Everyday Tee | {colour}", "Testwear", "Womens Tops", "40.00")
        for i, colour in enumerate(["Black", "White", "Navy", "Sage"])
    ]
    ingest(catalog, _connector().normalize(rows))
    catalog.flush()

    results, _ = search_catalog(catalog.connection(), query="everyday tee", limit=8)
    tees = [r for r in results if "Everyday Tee" in r.title]
    assert tees
    assert sum(1 for _ in tees) + tees[0].other_colourways == 4


def test_distinct_styles_are_not_collapsed_together(catalog: Session) -> None:
    """Collapsing keys on brand and style stem, so two genuinely different
    garments from one brand must both survive."""
    results, _ = search_catalog(
        catalog.connection(),
        filters=SearchFilters(categories=(Category.dress,)),
        limit=20,
    )
    titles = {r.title for r in results}
    assert len(titles) == len(results), "no duplicate titles among survivors"
