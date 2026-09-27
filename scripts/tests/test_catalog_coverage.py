"""Tests for the catalog coverage numbers, against the test database.

Every measure is an aggregate over a whole table, so each test empties the
catalog first: a row another test committed would otherwise land in the count.

Where a test pins one way of measuring against another - offers rather than
products, every offer rather than the sized categories, offers with an unknown
category in rather than out, present sizes rather than buyable ones - the
alternative is computed from the same seeded catalog rather than written down. A
constant would go on passing after the seed changed underneath it.
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

# The categories ROADMAP.md §5.1's correction leaves out, as SQL literals, taken
# from the module's tuple so a test cannot be measuring a different exclusion
# from the report.
UNSIZED = ", ".join(f"'{category.value}'" for category in catalog_coverage.UNSIZED_CATEGORIES)

# The reading before ROADMAP.md §5.1's correction of 2026-09-22: every offer in
# the denominator, whatever its category says about whether it can carry a size.
OFFERS_IN_EVERY_CATEGORY = text(
    """
    select 100.0 * count(sized.offer_id) / nullif(count(*), 0)
    from offers
    left join (select distinct offer_id from offer_sizes) as sized on sized.offer_id = offers.id
    """
)

# The same measure with the offers whose category is unknown dropped, which is
# the reading this report declines to take.
OFFERS_WITH_A_KNOWN_SIZED_CATEGORY = text(
    f"""
    select 100.0 * count(sized.offer_id) / nullif(count(*), 0)
    from offers
    join products on products.id = offers.product_id
    left join (select distinct offer_id from offer_sizes) as sized on sized.offer_id = offers.id
    where products.category is not null
      and products.category::text not in ({UNSIZED})
    """
)

# The measure as it read while availability was part of it: a size row search
# would match, rather than a size row at all.
OFFERS_WITH_A_BUYABLE_SIZE = text(
    f"""
    select 100.0 * count(buyable.offer_id) / nullif(count(*), 0)
    from offers
    join products on products.id = offers.product_id
    left join (
        select distinct offer_id from offer_sizes where in_stock is true or in_stock is null
    ) as buyable on buyable.offer_id = offers.id
    where products.category is null
       or products.category::text not in ({UNSIZED})
    """
)

TOTAL_OFFERS = text("select count(*) from offers")

SIZE_COVERAGE = "Offers with size data"


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
    """Five products over four titles, seven offers, five of them sized.

    Built so every decision the size measure makes changes an answer:

    - One product is a bag, whose category carries no size (ROADMAP.md §5.1's
      correction). Its offer is sized anyway, so leaving the category out cannot
      be mistaken for leaving unsized rows out.
    - One product has no category and two offers, one sized and one not, so
      keeping them in the denominator reads differently from dropping them.
    - One offer is sized and sold out, so counting present sizes reads
      differently from counting buyable ones.
    - One product carries three offers of which one is sized, and that one is
      sized twice: an offer sized S and M is one offer with size data, not two.
    - Two products share a title the way two colourways of one style do.
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
            ("e", toteme.id, "Coverage test bag", Category.bag),
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
            ("d2", "d"),
            ("e1", "e"),
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
            # a1 is buyable twice over: one size in stock, one of unknown stock.
            # a2 and d2 are buyable in exactly one size. b1 is sized and sold
            # out. e1 is the bag, sized, and out of the measure regardless.
            for source_id, size_value, in_stock in (
                ("a1", "S", True),
                ("a1", "M", None),
                ("a2", "L", True),
                ("b1", "M", False),
                ("d2", "S", True),
                ("e1", "M", True),
            )
        ]
    )
    session.flush()
    return session


def test_products_and_brands_count_the_catalog(seeded: Session) -> None:
    measured = _measured(seeded)
    assert measured["Products"].value == 5
    assert measured["Products"].met is False
    # Two of the five products are one style in two colourways, so the catalog
    # holds four titles.
    assert measured["Products"].qualifier == "across 4 titles"
    # The uncategorized product is unbranded too, and the two products sharing
    # one brand contribute it once.
    assert measured["Brands with products"].value == 2
    assert measured["Brands with products"].qualifier == ""


def test_category_coverage_is_the_share_of_products_with_a_category(seeded: Session) -> None:
    coverage = _measured(seeded)["Products with a resolved category"]
    assert coverage.value == 80.0
    assert coverage.qualifier == "of 5 products"


def test_size_coverage_counts_offers_rather_than_products(seeded: Session) -> None:
    coverage = _measured(seeded)[SIZE_COVERAGE]
    # Four of six offers in the denominator carry size data; three of five
    # products do. The seed is built so the two answers differ.
    assert coverage.value == pytest.approx(100.0 * 4 / 6)
    assert coverage.qualifier == "of 6 offers not in an unsized category"


def test_a_category_that_carries_no_size_is_out_of_the_denominator(seeded: Session) -> None:
    """The bag's offer is sized, and still out: the exclusion is about the category."""
    coverage = _measured(seeded)[SIZE_COVERAGE]
    size_picture = catalog_coverage.measure_sizes(seeded.connection())

    assert size_picture.unsized_category_offers == 1
    assert size_picture.unsized_category_sized_offers == 1
    # Six of the seven offers are measured, and counting the seventh would read
    # higher, because the one left out is one of the sized ones.
    assert _share(seeded, TOTAL_OFFERS) == 7
    assert coverage.value < _share(seeded, OFFERS_IN_EVERY_CATEGORY)


def test_an_offer_whose_category_is_unknown_stays_in_the_denominator(seeded: Session) -> None:
    """Null is unknown, not known-unsized, so dropping it would flatter the measure."""
    coverage = _measured(seeded)[SIZE_COVERAGE]
    size_picture = catalog_coverage.measure_sizes(seeded.connection())
    without = _share(seeded, OFFERS_WITH_A_KNOWN_SIZED_CATEGORY)

    assert size_picture.unplaced_offers == 2
    assert coverage.value < without
    # The report prints what the measure would read if they were dropped, so the
    # choice is visible in the output rather than only in the docstring.
    assert size_picture.share_without_unplaced == pytest.approx(without)


def test_availability_is_not_part_of_the_size_measure(seeded: Session) -> None:
    """A sold-out size is size data: the correction puts stock in C4, not C2."""
    coverage = _measured(seeded)[SIZE_COVERAGE]
    size_picture = catalog_coverage.measure_sizes(seeded.connection())
    buyable = _share(seeded, OFFERS_WITH_A_BUYABLE_SIZE)

    assert coverage.value > buyable
    assert size_picture.buyable_share == pytest.approx(buyable)
    # One offer is sized and sold out in every size; two are buyable in exactly
    # one size, where the offer sized S and M is not.
    assert size_picture.sold_out_offers == 1
    assert size_picture.one_size_offers == 2


def test_every_category_is_listed_even_with_no_products(seeded: Session) -> None:
    rows = catalog_coverage.by_category(seeded.connection())
    assert [row.category for row in rows] == [member.value for member in Category]
    assert {row.category: row.products for row in rows} == {
        member.value: {"dress": 2, "jeans": 1, "bag": 1}.get(member.value, 0) for member in Category
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
    assert catalog_coverage.measure_sizes(session.connection()) == catalog_coverage.SizePicture(
        unsized_category_offers=0,
        unsized_category_sized_offers=0,
        unplaced_offers=0,
        share_without_unplaced=None,
        buyable_share=None,
        sold_out_offers=0,
        one_size_offers=0,
    )

    lines = catalog_coverage.report(session.connection(), NOW).splitlines()
    assert "| Products with a resolved category | unknown | 95.0% | unknown |" in lines
    assert "  Dropped, the measure would read unknown instead." in lines


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

    assert "Milestone C2 (ROADMAP.md §5.1, corrected 2026-09-22), measured" in lines[2]
    assert "| Products | 5 across 4 titles | 25,000 | no |" in lines
    assert "| Brands with products | 2 | 50 | no |" in lines
    assert "| Products with a resolved category | 80.0% of 5 products | 95.0% | no |" in lines
    assert (
        f"| {SIZE_COVERAGE} | 66.7% of 6 offers not in an unsized category | 90.0% | no |" in lines
    )
    assert "| dress | 2 |" in lines
    assert "| top | 0 |" in lines


def test_the_report_keeps_the_c4_signals_apart_from_the_c2_criterion(seeded: Session) -> None:
    report = catalog_coverage.report(seeded.connection(), NOW)
    stock, sizes = report.split("## What the size measure counts")

    # The buyable share is reported, under a heading and a note that say twice
    # over that it is not what C2 is scored on.
    assert "## Not scored against C2: stock, which C4 owns" in stock
    assert "| Carrying a size in stock or of unknown stock | 50.0% |" in stock
    assert "**Not a C2 criterion, and not a second reading of one.**" in stock
    assert "say nothing about whether C2 is met" in stock
    # An offer buyable in one size counts the same as a full size run, which the
    # share above cannot show and the report says out loud.
    assert "| Buyable in exactly one size | 2 |" in stock

    # The offers the measure is and is not over, with the reading not taken.
    assert "1 offers are in the categories the correction excludes" in sizes
    assert "1 of them carry a size row" in sizes
    assert "2 offers have a product with no category at all" in sizes
    assert "Dropped, the measure would read 75.0% instead." in sizes
    assert "not always an ingestion gap" in sizes
