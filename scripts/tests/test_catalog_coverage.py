"""Tests for the catalog coverage numbers, against the test database.

Every measure is an aggregate over a whole table, so each test empties the
catalog first: a row another test committed would otherwise land in the count.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from api.genesis_api.models import Brand, Offer, OfferSize, Product, Retailer
from api.genesis_api.models.enums import Category, Provenance, SizeSystem
from scripts import catalog_coverage

NOW = datetime.datetime(2026, 9, 19, 12, 0, tzinfo=datetime.UTC)

# The seeded catalog: two of the four products carry a sized offer, so a measure
# that counted products rather than offers would report this instead of 40%.
PRODUCTS_WITH_SIZED_OFFERS = 50.0


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


@pytest.fixture
def seeded(session: Session) -> Session:
    """Four products over two brands, five offers, two of them sized.

    One product is unbranded and uncategorized, one carries three offers of which
    only the first is sized, and that first offer is sized twice - an offer sized
    S and M is one offer with size data, not two.
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
            title=f"Coverage test {source_id}",
            category=category,
        )
        for source_id, brand_id, category in (
            ("a", ganni.id, Category.dress),
            ("b", ganni.id, Category.dress),
            ("c", toteme.id, Category.jeans),
            ("d", None, None),
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
            )
            for source_id, size_value in (("a1", "S"), ("a1", "M"), ("b1", "M"))
        ]
    )
    session.flush()
    return session


def test_products_and_brands_count_the_catalog(seeded: Session) -> None:
    measured = _measured(seeded)
    assert measured["Products"].value == 4
    assert measured["Products"].met is False
    # The unbranded product contributes no brand, and the two products sharing
    # one brand contribute it once.
    assert measured["Brands with products"].value == 2


def test_category_coverage_is_the_share_of_products_with_a_category(seeded: Session) -> None:
    assert _measured(seeded)["Products with a resolved category"].value == 75.0


def test_size_coverage_counts_offers_rather_than_products(seeded: Session) -> None:
    coverage = _measured(seeded)["Offers with size data"]
    assert coverage.value == 40.0
    assert coverage.value != PRODUCTS_WITH_SIZED_OFFERS


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
    assert measured["Offers with size data"].value is None

    lines = catalog_coverage.report(session.connection(), NOW).splitlines()
    assert "| Products with a resolved category | unknown | 95.0% | unknown |" in lines


def test_a_value_that_reaches_its_target_is_met() -> None:
    products = _measure("Products")
    assert catalog_coverage.Coverage(measure=products, value=products.target).met is True
    assert catalog_coverage.Coverage(measure=products, value=products.target - 1).met is False


def test_the_report_states_every_measure_beside_its_target(seeded: Session) -> None:
    lines = catalog_coverage.report(seeded.connection(), NOW).splitlines()

    assert "Milestone C2 (ROADMAP.md §5.1), measured 2026-09-19 12:00 UTC against" in lines[2]
    assert "| Products | 4 | 25,000 | no |" in lines
    assert "| Brands with products | 2 | 50 | no |" in lines
    assert "| Products with a resolved category | 75.0% | 95.0% | no |" in lines
    assert "| Offers with size data | 40.0% | 90.0% | no |" in lines
    assert "| dress | 2 |" in lines
    assert "| top | 0 |" in lines
