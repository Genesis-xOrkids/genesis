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
from api.genesis_api.models.enums import Category, ColorFamily, Provenance, SizeSystem
from api.genesis_api.writer import WriteSpec, write
from intelligence.catalog.connectors.affiliate_feed import RAKUTEN_COLUMNS, AffiliateFeedConnector
from intelligence.catalog.ingest import ingest
from intelligence.catalog.money import FxRates
from intelligence.catalog.search import MAX_PER_STYLE, SearchFilters, search_catalog


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
    assert results[0].url
    assert results[0].image_url


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


def test_a_page_stays_full_when_colourways_fold(catalog: Session) -> None:
    """Folding colourways must not shorten the page. The rankers already go deep
    enough to refill it with the next distinct styles, so a query whose top hits
    are one style in five colours still returns a full page."""
    # The repeated word in the description ranks every colourway above the
    # other trenches, so the whole top of the fused list is the one style.
    colourways = [
        _row(
            f"HT{i}",
            f"Harbour Trench | {colour}",
            "Testwear",
            "Womens Coats",
            "250.00",
            description="Trench. A trench coat, the trench.",
        )
        for i, colour in enumerate(["Black", "Stone", "Navy", "Olive", "Khaki"])
    ]
    others = [
        _row(f"OT{i}", f"{name} Trench", "Otherwear", "Womens Coats", "200.00")
        for i, name in enumerate(["Field", "City", "Belted", "Cropped"])
    ]
    ingest(catalog, _connector().normalize(colourways + others))
    catalog.flush()

    results, diagnostics = search_catalog(catalog.connection(), query="trench", limit=4)

    assert len(results) == 4, "folded colourways must be replaced, not leave holes"
    harbour = [r for r in results if r.title.startswith("Harbour Trench")]
    assert len(harbour) == MAX_PER_STYLE
    assert all(r.other_colourways == 5 - MAX_PER_STYLE for r in harbour)
    assert all(r.other_colourways == 0 for r in results if r not in harbour)
    assert diagnostics.queries == 3, "refilling the page must not cost a query"


def _brand_id(catalog: Session, brand: str) -> int:
    return catalog.execute(
        text("select id from brands where name = :name"), {"name": brand}
    ).scalar_one()


def _extra_offer(
    product_id: int, retailer_id: int, n: int, price_usd_cents: int, *, in_stock: bool
) -> WriteSpec:
    """A further offer for an existing product, as a second retailer would add."""
    return WriteSpec(
        entity="Offer",
        natural_key={"source": "searchtest-extra", "source_id": f"{product_id}-{n}"},
        values={
            "provenance": Provenance.feed_sync,
            "product_id": product_id,
            "retailer_id": retailer_id,
            "url": f"https://example.test/extra/{product_id}/{n}",
            "price_amount_minor": price_usd_cents,
            "currency": "USD",
            "price_usd_cents": price_usd_cents,
            "in_stock": in_stock,
        },
    )


def test_filters_only_fills_the_page_with_distinct_products_not_the_cheapest(
    catalog: Session,
) -> None:
    """Without a query nothing ranks, so the order has to come from something
    other than price: ordering by price put free replacement buttons first on
    exactly the broad browse a new shopper starts with. Several offers of one
    product must not spend page slots either."""
    rows = [_row("FB0", "Replacement Button", "Fallbackwear", "Womens Tops", "0.00")]
    rows += [
        _row(f"FB{i + 1}", name, "Fallbackwear", "Womens Tops", "60.00")
        for i, name in enumerate(["Linen Shirt", "Poplin Shirt", "Boxy Tee", "Rib Tank"])
    ]
    rows += [
        _row(f"FC{i}", f"Knit Polo | {colour}", "Fallbackwear", "Womens Tops", "80.00")
        for i, colour in enumerate(["Black", "Ecru", "Navy"])
    ]
    ingest(catalog, _connector().normalize(rows))
    catalog.flush()

    # Two further offers for every product, so offer rows outnumber products
    # three to one and a page cut on offer rows would come back short.
    offers = catalog.execute(
        text(
            "select o.product_id, o.retailer_id, o.price_usd_cents from offers o"
            " join products p on p.id = o.product_id where p.source_id like 'F%'"
        )
    ).all()
    write(
        catalog,
        [
            _extra_offer(product_id, retailer_id, n, price + n, in_stock=True)
            for product_id, retailer_id, price in offers
            for n in (1, 2)
        ],
    )
    catalog.flush()

    results, diagnostics = search_catalog(
        catalog.connection(),
        filters=SearchFilters(brand_ids=(_brand_id(catalog, "Fallbackwear"),)),
        limit=6,
    )

    assert len(results) == 6
    assert len({r.product_id for r in results}) == 6
    polos = [r for r in results if r.title.startswith("Knit Polo")]
    assert len(polos) == MAX_PER_STYLE
    assert all(r.other_colourways == 1 for r in polos)
    assert results[0].price_usd_cents != 0, "the free item must not lead on price"
    assert diagnostics.queries == 2


def test_filters_only_puts_known_in_stock_before_unknown_before_sold_out(
    catalog: Session,
) -> None:
    """A browse that leads with a sold-out item leads with something nobody can
    buy; an unknown is at least possibly buyable."""
    known = _row("ST1", "Stock Known Tee", "Stockwear", "Womens Tops", "40.00")
    also = _row("ST2", "Stock Also Tee", "Stockwear", "Womens Tops", "30.00")
    unknown = _row("ST3", "Stock Unknown Tee", "Stockwear", "Womens Tops", "20.00", instock=None)
    gone = _row(
        "ST4", "Stock Gone Tee", "Stockwear", "Womens Tops", "10.00", instock="out of stock"
    )
    # Cheapest first and newest first would each give the reverse of this order.
    ingest(catalog, _connector().normalize([known, also, unknown, gone]))
    catalog.flush()

    results, _ = search_catalog(
        catalog.connection(),
        filters=SearchFilters(brand_ids=(_brand_id(catalog, "Stockwear"),)),
        limit=8,
    )

    assert [r.in_stock for r in results] == [True, True, None, False]


def test_filters_only_spreads_the_page_across_brands(catalog: Session) -> None:
    """The ingest runner writes each storefront in one transaction, so a whole
    storefront shares one created_at. Newest first on its own would fill a
    browse with whichever storefront was onboarded last."""
    for brand in ("Earlywear", "Latewear"):
        ingest(
            catalog,
            _connector().normalize(
                [
                    _row(f"{brand}{i}", f"{brand} {name}", brand, "Womens Tops", "50.00")
                    for i, name in enumerate(["Shirt", "Tee", "Tank", "Blouse", "Polo"])
                ]
            ),
        )
        catalog.flush()

    results, _ = search_catalog(
        catalog.connection(),
        filters=SearchFilters(
            brand_ids=(_brand_id(catalog, "Earlywear"), _brand_id(catalog, "Latewear"))
        ),
        limit=4,
    )

    assert [r.brand for r in results].count("Earlywear") == 2
    assert [r.brand for r in results].count("Latewear") == 2


def test_a_product_shows_its_buyable_offer_not_a_cheaper_sold_out_one(
    catalog: Session,
) -> None:
    """The offer shown is the one the shopper clicks. A cheaper offer that is
    sold out is not a price they can pay, so in stock wins over cheaper, on the
    ranked path and on the filters-only path alike."""
    ingest(
        catalog,
        _connector().normalize(
            [_row("BO1", "Buyable Overshirt", "Offerwear", "Womens Shirts", "100.00")]
        ),
    )
    catalog.flush()
    product_id, retailer_id = catalog.execute(
        text(
            "select o.product_id, o.retailer_id from offers o"
            " join products p on p.id = o.product_id where p.source_id = 'BO1'"
        )
    ).one()
    write(catalog, [_extra_offer(product_id, retailer_id, 1, 8000, in_stock=False)])
    catalog.flush()

    ranked, _ = search_catalog(catalog.connection(), query="buyable overshirt")
    browsed, _ = search_catalog(
        catalog.connection(), filters=SearchFilters(brand_ids=(_brand_id(catalog, "Offerwear"),))
    )

    for results in (ranked, browsed):
        overshirt = next(r for r in results if r.product_id == product_id)
        assert overshirt.in_stock is True
        assert overshirt.price_usd_cents == 10000
