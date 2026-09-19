"""What the catalog covers against milestone C2's targets, computed in SQL.

    PYTHONPATH=. uv run python -m scripts.catalog_coverage

C2 asks for a catalog that can dress someone: 25,000 products across 50 brands,
at least 95% of products carrying a resolved category and at least 90% carrying
usable size data (ROADMAP.md §5.1, and §3 for the first two). This prints each of
the four beside its target and whether it is met, so the milestone is measured
rather than asserted.

Size coverage is the share of *offers* that carry a size, not of products. Sizes
hang off offers because an offer is the unit somebody buys, and one style can be
fully sized at one retailer and barely sized at another; each measure is quoted
the way its own table states it.

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

from sqlalchemy import TextClause, text
from sqlalchemy.engine import Connection

from api.genesis_api.db import engine

PERCENT = "%"


@dataclass(frozen=True)
class Measure:
    """One of C2's four targets and the statement that measures it."""

    name: str
    statement: TextClause
    target: float
    unit: str


MEASURES = (
    Measure(
        name="Products",
        statement=text("select count(*) from products"),
        target=25_000,
        unit="",
    ),
    Measure(
        name="Brands with products",
        # The brands the catalog can dress from, which is what "25,000 products
        # across 50 brands" counts. A brand row nothing is sold under is not one
        # of them, and a product whose brand is unknown carries a null that
        # `count(distinct ...)` leaves out.
        statement=text("select count(distinct brand_id) from products"),
        target=50,
        unit="",
    ),
    Measure(
        name="Products with a resolved category",
        # A null category is unknown, so counting the column counts the resolved
        # ones. Over an empty catalog the share is null too - unknown, not 0%.
        statement=text(
            "select round(100.0 * count(category) / nullif(count(*), 0), 1) from products"
        ),
        target=95,
        unit=PERCENT,
    ),
    Measure(
        name="Offers with size data",
        # Distinct offer ids rather than a join straight to offer_sizes: an offer
        # sized S, M and L is one offer with size data, not three.
        statement=text(
            """
            select round(100.0 * count(sized.offer_id) / nullif(count(*), 0), 1)
            from offers
            left join (select distinct offer_id from offer_sizes) as sized
                on sized.offer_id = offers.id
            """
        ),
        target=90,
        unit=PERCENT,
    ),
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
    """What one measure came to. A null value is unknown: there was nothing to measure."""

    measure: Measure
    value: float | None

    @property
    def met(self) -> bool | None:
        """Whether the value clears its target, or None while the value is unknown."""
        return None if self.value is None else self.value >= self.measure.target


@dataclass(frozen=True)
class CategoryProducts:
    """One garment category and how many products carry it."""

    category: str
    products: int


def coverages(connection: Connection) -> list[Coverage]:
    """Every C2 measure, one statement each."""
    return [
        Coverage(measure=measure, value=_float(connection.execute(measure.statement).scalar_one()))
        for measure in MEASURES
    ]


def by_category(connection: Connection) -> list[CategoryProducts]:
    """Every category the taxonomy defines and its product count, in taxonomy order."""
    return [
        CategoryProducts(category=row["category"], products=row["products"])
        for row in connection.execute(BY_CATEGORY).mappings()
    ]


def report(connection: Connection, now: datetime.datetime) -> str:
    """The markdown report: C2's four measures, then every category's product count."""
    lines = [
        "# Catalog coverage",
        "",
        f"Milestone C2 (ROADMAP.md §5.1), measured "
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


def _float(value: object) -> float | None:
    return None if value is None else float(str(value))


def _source(connection: Connection) -> str:
    """Which database the numbers came from, named without its credentials."""
    url = connection.engine.url
    return f"{url.database} at {url.host}"


def _stated(value: float, unit: str) -> str:
    """A number as the report states it: percentages to one decimal, counts whole."""
    return f"{value:,.1f}{unit}" if unit else f"{value:,.0f}"


def _measured(coverage: Coverage) -> str:
    return "unknown" if coverage.value is None else _stated(coverage.value, coverage.measure.unit)


def _met(coverage: Coverage) -> str:
    if coverage.met is None:
        return "unknown"
    return "yes" if coverage.met else "no"


def main() -> None:
    with engine().connect() as connection:
        print(report(connection, datetime.datetime.now(datetime.UTC)))


if __name__ == "__main__":
    main()
