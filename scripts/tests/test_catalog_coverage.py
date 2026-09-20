"""Tests for the catalog coverage numbers, against the test database.

Every measure is an aggregate over a whole table, so each test empties the
catalog first: a row another test committed would otherwise land in the count.

Where a test pins one way of measuring against another - offers rather than
products, usable sizes rather than every size row - the alternative is computed
from the same seeded catalog rather than written down. A constant would go on
passing after the seed changed underneath it.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import TextClause, delete, text
from sqlalchemy.orm import Session

from api.genesis_api.models import Brand, Offer, OfferSize, Product, Retailer
from api.genesis_api.models.enums import Category, Provenance, SizeSystem
from scripts import catalog_coverage

NOW = datetime.datetime(2026, 9, 19, 12, 0, tzinfo=datetime.UTC)

# The same share the report measures, taken over products instead of offers.
PRODUCTS_WITH_USABLE_SIZES = text(
    """
    select 100.0 * (
        select count(distinct product_id) from offers
        where id in (
            select offer_id from offer_sizes where in_stock is true or in_stock is null
        )
    ) / nullif((select count(*) from products), 0)
    """
)

# The same share taken over every size row, sold out or not.
OFFERS_WITH_ANY_SIZE_ROW = text(
    """
    select 100.0 * count(sized.offer_id) / nullif(count(*), 0)
    from offers
    left join (select distinct offer_id from offer_sizes) as sized on sized.offer_id = offers.id
    """
)

SIZE_COVERAGE = "Offers with usable size data"


def _empty(session: Session) -> None:
    """Clear the catalog, so what the measures see is only what a test put there."""
    session.execute(delete(Offer))
    session.execute(delete(Product))


def _measure(name: str) -> catalog_coverage.Measure:
    return next(measure for measure in catalog_coverage.MEASURES if measure.name == name)


def _measured(session: Session) -> dict[str, catalog_coverage.Coverage]:
    return {
        coverage.measure.name: coverage
        for coverage in catalog_coverage.coverages(session.connection())
    }


def _share(session: Session, statement: TextClause) -> float:
    return float(session.connection().execute(statement).scalar_one())


def _coverage(measure: catalog_coverage.Measure, value: float) -> catalog_coverage.Coverage:
    return catalog_coverage.Coverage(measure=measure, value=value, qualifier="")


@pytest.fixture
def seeded(session: Session) -> Session:
    """Four products over three titles and two brands, five offers, two of them sized.

    One product is unbranded and uncategorized, and two share a title the way two
    colourways of one style do. One product carries three offers of which only the
    first is sized, and that one is sized twice - an offer sized S and M is one
    offer with size data, not two. The other sized offer has sold out, so it
    carries size data search cannot use.
    """
    _empty(session)

    ganni = Brand(slug="ganni-coverage-test", name="Ganni")
    toteme = Brand(slug="toteme-coverage-test", name="Toteme")
    retailer = Retailer(slug="net-a-porter-coverage-test", name="Net-a-Porter")
    session.add_all([ganni, toteme, retailer])
    session.flush()

    products = [
        Product(
            source="coverage-test",
            source_id=source_id,
            provenance=Provenance.feed_sync,
            brand_id=brand_id,
            title=title,
            category=category,
        )
        for source_id, brand_id, title, category in (
            ("a", ganni.id, "Coverage test dress", Category.dress),
            ("b", ganni.id, "Coverage test dress", Category.dress),
            ("c", toteme.id, "Coverage test jeans", Category.jeans),
            ("d", None, "Coverage test unknown", None),
        )
    ]
    session.add_all(products)
    session.flush()

    by_source_id = {product.source_id: product for product in products}
    offers = [
        Offer(
            source="coverage-test",
            source_id=source_id,
            provenance=Provenance.feed_sync,
            product_id=by_source_id[product_source_id].id,
            retailer_id=retailer.id,
            url="https://example.test/p",
            price_amount_minor=29500,
            currency="USD",
        )
        for source_id, product_source_id in (
            ("a1", "a"),
            ("a2", "a"),
            ("a3", "a"),
            ("b1", "b"),
            ("d1", "d"),
        )
    ]
    session.add_all(offers)
    session.flush()

    by_offer_source_id = {offer.source_id: offer for offer in offers}
    session.add_all(
        [
            OfferSize(
                offer_id=by_offer_source_id[source_id].id,
                size_system=SizeSystem.alpha,
                size_value=size_value,
                in_stock=in_stock,
            )
            # a1 is usable twice over: one size in stock, one of unknown stock.
            # b1 is sized and sold out.
            for source_id, size_value, in_stock in (
                ("a1", "S", True),
                ("a1", "M", None),
                ("b1", "M", False),
            )
        ]
    )
    session.flush()
    return session


def test_products_and_brands_count_the_catalog(seeded: Session) -> None:
    measured = _measured(seeded)
    assert measured["Products"].value == 4
    assert measured["Products"].met is False
    # Two of the four products are one style in two colourways, so the catalog
    # holds three titles.
    assert measured["Products"].qualifier == "across 3 titles"
    # The unbranded product contributes no brand, and the two products sharing
    # one brand contribute it once.
    assert measured["Brands with products"].value == 2
    assert measured["Brands with products"].qualifier == ""


def test_category_coverage_is_the_share_of_products_with_a_category(seeded: Session) -> None:
    coverage = _measured(seeded)["Products with a resolved category"]
    assert coverage.value == 75.0
    assert coverage.qualifier == "of 4 products"


def test_size_coverage_counts_offers_rather_than_products(seeded: Session) -> None:
    coverage = _measured(seeded)[SIZE_COVERAGE]
    # One of five offers carries a size somebody could buy; one of four products
    # does. The seed is built so the two answers differ.
    assert coverage.value == 20.0
    assert _share(seeded, PRODUCTS_WITH_USABLE_SIZES) == 25.0
    assert coverage.value != _share(seeded, PRODUCTS_WITH_USABLE_SIZES)
    assert coverage.qualifier == "of 5 offers"


def test_a_sold_out_size_is_not_usable_size_data(seeded: Session) -> None:
    coverage = _measured(seeded)[SIZE_COVERAGE]
    # Two offers carry size rows and one of them has sold out, so counting every
    # size row would report double what search can actually match.
    assert _share(seeded, OFFERS_WITH_ANY_SIZE_ROW) == 40.0
    assert coverage.value == 20.0

    sizes = catalog_coverage.sized_offers(seeded.connection())
    assert (sizes.sized, sizes.sold_out) == (2, 1)


def test_every_category_is_listed_even_with_no_products(seeded: Session) -> None:
    rows = catalog_coverage.by_category(seeded.connection())
    assert [row.category for row in rows] == [member.value for member in Category]
    assert {row.category: row.products for row in rows} == {
        member.value: {"dress": 2, "jeans": 1}.get(member.value, 0) for member in Category
    }


def test_an_empty_catalog_measures_unknown_rather_than_zero(session: Session) -> None:
    _empty(session)
    measured = _measured(session)

    assert measured["Products"].value == 0
    assert measured["Products"].met is False
    # No products is a known zero; the share of nothing is unknown, not 0%.
    assert measured["Products with a resolved category"].value is None
    assert measured["Products with a resolved category"].met is None
    assert measured[SIZE_COVERAGE].value is None
    assert catalog_coverage.sized_offers(session.connection()) == catalog_coverage.SizedOffers(
        sized=0, sold_out=0
    )

    lines = catalog_coverage.report(session.connection(), NOW).splitlines()
    assert "| Products with a resolved category | unknown | 95.0% | unknown |" in lines


def test_a_value_that_reaches_its_target_is_met() -> None:
    products = _measure("Products")
    assert _coverage(products, products.target).met is True
    assert _coverage(products, products.target - 1).met is False


def test_a_share_that_displays_as_its_target_can_still_miss_it() -> None:
    """19,992 of 21,055 products is 94.9513%, which displays as 95.0% against a 95% target."""
    category = _measure("Products with a resolved category")
    coverage = _coverage(category, 100.0 * 19_992 / 21_055)
    assert round(coverage.value, 1) == category.target
    assert coverage.met is False


def test_the_report_states_every_measure_beside_its_target(seeded: Session) -> None:
    lines = catalog_coverage.report(seeded.connection(), NOW).splitlines()

    assert "Milestone C2 (ROADMAP.md §5.1), measured 2026-09-19 12:00 UTC against" in lines[2]
    assert "| Products | 4 across 3 titles | 25,000 | no |" in lines
    assert "| Brands with products | 2 | 50 | no |" in lines
    assert "| Products with a resolved category | 75.0% of 4 products | 95.0% | no |" in lines
    assert f"| {SIZE_COVERAGE} | 20.0% of 5 offers | 90.0% | no |" in lines
    assert "| dress | 2 |" in lines
    assert "| top | 0 |" in lines


def test_the_report_names_both_sources_of_the_size_criterion(seeded: Session) -> None:
    report = catalog_coverage.report(seeded.connection(), NOW)

    assert "ROADMAP.md §5.1 states the 90% over products" in report
    assert "second-brain/wiki/projects/catalog-supply.md" in report
    # The offers a reader would otherwise have to go and count themselves.
    assert "2 offers carry a size row" in report
    assert "sizes have sold out on 1 of them" in report
