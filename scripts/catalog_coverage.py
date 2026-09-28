"""What the catalog covers against milestone C2's targets, computed in SQL.

    PYTHONPATH=. uv run python -m scripts.catalog_coverage

C2 asks for a catalog that can dress someone: 25,000 products across 50 brands,
at least 95% of products carrying a resolved category and at least 90% carrying
usable size data (ROADMAP.md §5.1, and §3 for the first two). This prints each of
the four beside its target and whether it is met, so the milestone is measured
rather than asserted.

ROADMAP.md §5.1's correction of 2026-09-22 settles what the fourth one counts,
and this follows it rather than deciding anything of its own:

- **Usable size data means size data present**, over **offers whose category
  carries sizes**. Bags, belts, jewellery, eyewear, watches and scarves are out
  of the denominator, because a size the garment does not have is not a gap this
  milestone can close.
- **Availability is not part of it.** An offer sized and sold out still counts:
  stock turns over hourly and a breadth milestone gated on it could never close.
  The share a shopper could actually buy prints beside the target as C4's signal,
  where it belongs, and is not scored against C2.

One question the correction leaves open, and how this answers it: **an offer
whose product has no category stays in the denominator**, because null is
unknown rather than known-unsized. Excluding it would let an unresolved category
hide a missing size, and would make this measure rise as C2's category measure
fell. The report prints how many offers that is and what the measure would read
without them, so the choice is auditable rather than asserted here.

A product row is one colourway, not one style, so the product count overstates
the options an outfit can draw on, and the distinct-title count prints beside it.

``met`` compares the unrounded share against the target and the report rounds for
display, so a share that displays as its target can still miss it. Rounding
first is how 94.95% passes a 95% criterion.

It also prints a product count for every category the taxonomy defines, zeros
included, so "every core garment category populated" is readable off the table.
Which categories a catalog that can dress someone needs, and in what proportion,
is a product decision, and this report does not make it: no ranking, no
threshold, no verdict on a thin category.

One statement per measure: Postgres counts, Python formats. It only reads.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from sqlalchemy import RowMapping, TextClause, text
from sqlalchemy.engine import Connection

from api.genesis_api.db import engine
from api.genesis_api.models.enums import Category

PERCENT = "%"

# Categories that carry no size, named by ROADMAP.md §5.1's correction of
# 2026-09-22 and taken from the enum rather than spelled out, so renaming a
# member here is a type error rather than a silently empty exclusion.
UNSIZED_CATEGORIES = (
    Category.bag,
    Category.belt,
    Category.jewelry,
    Category.eyewear,
    Category.watch,
    Category.scarf,
)
_UNSIZED = ", ".join(f"'{category.value}'" for category in UNSIZED_CATEGORIES)

# One row per offer, never one per size: an offer sized S, M and L carries size
# data once. Written as subqueries joined in rather than `id in (...)`, so each
# join is at most 1:1 and every count below counts offers.
ANY_SIZE = "select distinct offer_id from offer_sizes"
# A size row a size-filtered search will match, per intelligence/catalog/search.py:
# in stock, or of unknown stock. Called buyable rather than usable, because since
# the 2026-09-22 correction "usable size data" means present, whatever the stock.
BUYABLE_SIZES = (
    "select distinct offer_id from offer_sizes where in_stock is true or in_stock is null"
)
ONE_BUYABLE_SIZE = (
    "select offer_id from offer_sizes where in_stock is true or in_stock is null "
    "group by offer_id having count(*) = 1"
)

# Every offer with its category and the three facts about its sizes that C2 and
# C4 read. Defined once, so the measure and the signals printed beside it are
# taken over the same rows and cannot drift apart.
OFFER_SIZING = f"""
    select products.category::text as category,
           sized.offer_id is not null as sized,
           buyable.offer_id is not null as buyable,
           one_size.offer_id is not null as one_size
    from offers
    join products on products.id = offers.product_id
    left join ({ANY_SIZE}) as sized on sized.offer_id = offers.id
    left join ({BUYABLE_SIZES}) as buyable on buyable.offer_id = offers.id
    left join ({ONE_BUYABLE_SIZE}) as one_size on one_size.offer_id = offers.id
"""

# The population C2's size criterion is measured over: everything the correction
# did not exclude. An offer whose product has no category stays in, because null
# is unknown rather than known-unsized.
MAY_CARRY_SIZES = f"(category is null or category not in ({_UNSIZED}))"
# The same population with those unresolved offers dropped, which is the reading
# this report does not take. It prints it anyway, beside the count it is over, so
# the cost of that choice is a number rather than an argument.
KNOWN_SIZED_CATEGORY = f"(category is not null and category not in ({_UNSIZED}))"
UNSIZED_CATEGORY = f"category in ({_UNSIZED})"


# The prose under the stock table. No measured numbers in it: what it has to say
# is why three real numbers are not criteria, which is the mistake it exists to
# make impossible.
STOCK_NOTE = """\
**Not a C2 criterion, and not a second reading of one.** ROADMAP.md §5.1's correction of
2026-09-22 keeps availability out of C2 deliberately: stock turns over hourly, and a breadth
milestone gated on it could never close. These three are here because the first is what a
size-filtered search can actually return (`intelligence/catalog/search.py`), and because the
first hides the third - one size left counts the same as a full size run, while a shopper asks
for their own size. They are the numbers to watch once C4 starts, and on their own
say nothing about whether C2 is met."""

# The prose under the size measure: which offers it is over, and what an offer
# without a size row does and does not imply.
SIZE_NOTES = """\
- {unsized_category_offers} offers are in the categories the correction excludes: bag, belt,
  jewelry, eyewear, watch, scarf. {unsized_category_sized_offers} of them carry a size row
  anyway, a belt having a size, and the exclusion drops those too. It is a statement about the
  category, not about the row.
- {unplaced_offers} offers have a product with no category at all, so they can be placed neither
  inside nor outside those categories, and they stay in the denominator. Null is unknown, not
  known-unsized: dropping them would let an unresolved category hide a missing size, and would
  make this measure rise as C2's category measure fell.
  Dropped, the measure would read {share_without_unplaced} instead.
- An offer with no size row is not always an ingestion gap. The connector reads sizes only from
  an option named for the size, so it writes none for a single-variant `Default Title` product,
  which states that the listing has no options rather than that the garment is one size, and
  none for a label `parse_sizes` cannot read: a bare numeric with no declared system, or a size
  in a system the enum does not have (kids' ages, bra band and cup), stays unknown on purpose
  (`intelligence/catalog/connectors/shopify_public.py`, `intelligence/catalog/sizes.py`).
- A product row is one colourway of one style, so the product count overstates the options an
  outfit can draw on. The title count beside it is the nearer figure (C3,
  `second-brain/wiki/concepts/hybrid-catalog-search.md`).
- Met compares the unrounded share, so a share that displays as its target can still miss it."""


@dataclass(frozen=True)
class Measure:
    """One of C2's four targets and the statement that measures it.

    The statement returns a ``value``, and a ``basis`` wherever ``qualifier``
    names one: the number the value is out of, or the sharper number standing
    behind it.
    """

    name: str
    statement: TextClause
    target: float
    unit: str
    qualifier: str


MEASURES = (
    Measure(
        name="Products",
        # Distinct titles beside the row count, because a product row is one
        # colourway of one style: colourway splitting left 3,557 titles on more
        # than one product and one shoe on 49 of them (C3, hybrid-catalog-search).
        # Titles rather than (brand, title) pairs - the figure that defect is
        # tracked in, and the lower of the two, which differ by ten today.
        statement=text("select count(*) as value, count(distinct title) as basis from products"),
        target=25_000,
        unit="",
        qualifier="across {basis:,} titles",
    ),
    Measure(
        name="Brands with products",
        # The brands the catalog can dress from, which is what "25,000 products
        # across 50 brands" counts. A brand row nothing is sold under is not one
        # of them, and a product whose brand is unknown carries a null that
        # `count(distinct ...)` leaves out.
        statement=text("select count(distinct brand_id) as value from products"),
        target=50,
        unit="",
        qualifier="",
    ),
    Measure(
        name="Products with a resolved category",
        # A null category is unknown, so counting the column counts the resolved
        # ones. Over an empty catalog the share is null too - unknown, not 0%.
        statement=text(
            """
            select 100.0 * count(category) / nullif(count(*), 0) as value,
                   count(*) as basis
            from products
            """
        ),
        target=95,
        unit=PERCENT,
        qualifier="of {basis:,} products",
    ),
    Measure(
        # "Size data", not "usable size data": since the correction the two mean
        # the same thing, and the shorter name cannot be read as being about stock.
        name="Offers with size data",
        statement=text(
            f"""
            select 100.0 * count(*) filter (where sized) / nullif(count(*), 0) as value,
                   count(*) as basis
            from ({OFFER_SIZING}) as offer
            where {MAY_CARRY_SIZES}
            """
        ),
        target=90,
        unit=PERCENT,
        qualifier="of {basis:,} offers not in an unsized category",
    ),
)

# What the one size percentage above does not say: which offers it left out or
# kept on an unresolved category, and what stock says about the ones it counted.
SIZE_PICTURE = text(
    f"""
    select count(*) filter (where {UNSIZED_CATEGORY}) as unsized_category_offers,
           count(*) filter (where {UNSIZED_CATEGORY} and sized) as unsized_category_sized_offers,
           count(*) filter (where category is null) as unplaced_offers,
           100.0 * count(*) filter (where {KNOWN_SIZED_CATEGORY} and sized)
               / nullif(count(*) filter (where {KNOWN_SIZED_CATEGORY}), 0)
               as share_without_unplaced,
           100.0 * count(*) filter (where {MAY_CARRY_SIZES} and buyable)
               / nullif(count(*) filter (where {MAY_CARRY_SIZES}), 0) as buyable_share,
           count(*) filter (where {MAY_CARRY_SIZES} and sized and not buyable) as sold_out_offers,
           count(*) filter (where {MAY_CARRY_SIZES} and one_size) as one_size_offers
    from ({OFFER_SIZING}) as offer
    """
)

# Every member of the category enum, including the ones no product carries. The
# members come from the database's own type rather than from `Category` so the
# zeros are produced by the same statement as the counts; the two lists cannot
# disagree, because CI fails on any drift between the models and the schema.
BY_CATEGORY = text(
    """
    select member::text as category, count(products.id) as products
    from unnest(enum_range(null::category)) as member
    left join products on products.category = member
    group by member
    order by member
    """
)


@dataclass(frozen=True)
class Coverage:
    """What one measure came to, and the phrase saying what it is out of.

    A null value is unknown: there was nothing to measure. The qualifier is empty
    where the value stands alone.
    """

    measure: Measure
    value: float | None
    qualifier: str

    @property
    def met(self) -> bool | None:
        """Whether the value clears its target, or None while the value is unknown.

        Compares what was measured, not what is displayed: 94.95% misses a 95%
        target that the printed 95.0% would appear to clear.
        """
        return None if self.value is None else self.value >= self.measure.target


@dataclass(frozen=True)
class SizePicture:
    """Everything about sizes that C2's one percentage does not say.

    The first four are about the population: which offers the correction excluded,
    how many of those carry sizes anyway, how many are in on an unresolved
    category, and what the measure would read without those. The last three are
    stock, which C4 owns and C2 is deliberately blind to.

    Every field counts offers, except the two shares, which are percentages: one
    over the population the measure is taken over, one over that population
    without the offers whose category is unknown.
    """

    unsized_category_offers: int
    unsized_category_sized_offers: int
    unplaced_offers: int
    share_without_unplaced: float | None
    buyable_share: float | None
    sold_out_offers: int
    one_size_offers: int


@dataclass(frozen=True)
class CategoryProducts:
    """One garment category and how many products carry it."""

    category: str
    products: int


def coverages(connection: Connection) -> list[Coverage]:
    """Every C2 measure, one statement each."""
    return [
        _coverage(measure, connection.execute(measure.statement).mappings().one())
        for measure in MEASURES
    ]


def measure_sizes(connection: Connection) -> SizePicture:
    """The offers the size measure leaves out, and what stock says about the rest."""
    row = connection.execute(SIZE_PICTURE).mappings().one()
    return SizePicture(
        unsized_category_offers=row["unsized_category_offers"],
        unsized_category_sized_offers=row["unsized_category_sized_offers"],
        unplaced_offers=row["unplaced_offers"],
        share_without_unplaced=_float(row["share_without_unplaced"]),
        buyable_share=_float(row["buyable_share"]),
        sold_out_offers=row["sold_out_offers"],
        one_size_offers=row["one_size_offers"],
    )


def by_category(connection: Connection) -> list[CategoryProducts]:
    """Every category the taxonomy defines and its product count, in taxonomy order."""
    return [
        CategoryProducts(category=row["category"], products=row["products"])
        for row in connection.execute(BY_CATEGORY).mappings()
    ]


def report(connection: Connection, now: datetime.datetime) -> str:
    """C2's four measures, the stock C4 owns, what the size measure leaves out, categories."""
    size_picture = measure_sizes(connection)
    lines = [
        "# Catalog coverage",
        "",
        f"Milestone C2 (ROADMAP.md §5.1, corrected 2026-09-22), measured "
        f"{now.astimezone(datetime.UTC):%Y-%m-%d %H:%M} UTC against {_source(connection)}.",
        "",
        "| Measure | Actual | Target | Met |",
        "|---|--:|--:|---|",
    ]
    lines += [
        f"| {coverage.measure.name} | {_measured(coverage)}"
        f" | {_stated(coverage.measure.target, coverage.measure.unit)} | {_met(coverage)} |"
        for coverage in coverages(connection)
    ]
    lines += [
        "",
        "## Not scored against C2: stock, which C4 owns",
        "",
        "| C4 signal, over the same offers the size measure is taken over | Value |",
        "|---|--:|",
        f"| Carrying a size in stock or of unknown stock | {_share(size_picture.buyable_share)} |",
        f"| Sized, and sold out in every size | {size_picture.sold_out_offers:,} |",
        f"| Buyable in exactly one size | {size_picture.one_size_offers:,} |",
        "",
    ]
    lines += STOCK_NOTE.splitlines()
    lines += [
        "",
        "## What the size measure counts",
        "",
    ]
    lines += SIZE_NOTES.format(
        unsized_category_offers=f"{size_picture.unsized_category_offers:,}",
        unsized_category_sized_offers=f"{size_picture.unsized_category_sized_offers:,}",
        unplaced_offers=f"{size_picture.unplaced_offers:,}",
        share_without_unplaced=_share(size_picture.share_without_unplaced),
    ).splitlines()
    lines += [
        "",
        "## Products by category",
        "",
        "Every category the taxonomy defines, populated or not. Which of them a catalog that",
        "can dress someone needs, and in what proportion, is a product decision this report",
        "does not make.",
        "",
        "| Category | Products |",
        "|---|--:|",
    ]
    lines += [f"| {row.category} | {row.products:,} |" for row in by_category(connection)]
    return "\n".join(lines)


def _coverage(measure: Measure, row: RowMapping) -> Coverage:
    """One measured row, with its qualifier filled in from the same statement."""
    qualifier = measure.qualifier.format(basis=row["basis"]) if measure.qualifier else ""
    return Coverage(measure=measure, value=_float(row["value"]), qualifier=qualifier)


def _float(value: object) -> float | None:
    return None if value is None else float(str(value))


def _source(connection: Connection) -> str:
    """Which database the numbers came from, named without its credentials."""
    url = connection.engine.url
    return f"{url.database} at {url.host}"


def _stated(value: float, unit: str) -> str:
    """A number as the report states it: percentages to one decimal, counts whole."""
    return f"{value:,.1f}{unit}" if unit else f"{value:,.0f}"


def _share(value: float | None) -> str:
    return "unknown" if value is None else _stated(value, PERCENT)


def _measured(coverage: Coverage) -> str:
    if coverage.value is None:
        return "unknown"
    stated = _stated(coverage.value, coverage.measure.unit)
    return f"{stated} {coverage.qualifier}" if coverage.qualifier else stated


def _met(coverage: Coverage) -> str:
    if coverage.met is None:
        return "unknown"
    return "yes" if coverage.met else "no"


def main() -> None:
    with engine().connect() as connection:
        print(report(connection, datetime.datetime.now(datetime.UTC)))


if __name__ == "__main__":
    main()
