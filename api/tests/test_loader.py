"""The loader's central claim, measured.

"One query per requested relationship, never more" is an empirical claim about
the number of statements issued, so these tests count them. An N+1 regression
fails here as a number, rather than surfacing later as latency.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from api.genesis_api.graphql.loader import Selection, instantiate, load_rows
from api.genesis_api.models import (
    Brand,
    Offer,
    Product,
    Retailer,
)
from api.genesis_api.models.enums import Category, ColorFamily, Gender, Provenance, Silhouette


@pytest.fixture
def seeded(session: Session) -> dict[str, int]:
    """Two brands, three products, four offers across two retailers."""
    session.execute(delete(Offer))
    session.execute(delete(Product))

    ganni = Brand(slug="ganni-test", name="Ganni")
    toteme = Brand(slug="toteme-test", name="Toteme")
    net = Retailer(slug="net-a-porter-test", name="Net-a-Porter")
    ssense = Retailer(slug="ssense-test", name="SSENSE")
    session.add_all([ganni, toteme, net, ssense])
    session.flush()

    products = [
        Product(
            source="test",
            source_id=f"p{i}",
            provenance=Provenance.feed_sync,
            brand_id=ganni.id if i < 2 else toteme.id,
            title=f"Test product {i}",
            category=Category.dress,
            gender=Gender.womens,
            silhouette=Silhouette.a_line,
            color_hex="#1a1a1a",
            color_family=ColorFamily.black,
        )
        for i in range(3)
    ]
    session.add_all(products)
    session.flush()

    offers = []
    for index, product in enumerate(products):
        for retailer in (net, ssense):
            if index == 2 and retailer is ssense:
                continue
            offers.append(
                Offer(
                    source="test",
                    source_id=f"o{product.id}-{retailer.id}",
                    provenance=Provenance.feed_sync,
                    product_id=product.id,
                    retailer_id=retailer.id,
                    url="https://example.test/p",
                    price_amount_minor=29500,
                    currency="USD",
                    price_usd_cents=29500,
                    in_stock=True,
                )
            )
    session.add_all(offers)
    session.flush()
    return {"ganni": ganni.id, "toteme": toteme.id, "product_count": len(products)}


def test_scalar_only_selection_issues_one_query(session: Session, seeded: dict[str, int]) -> None:
    selection = Selection(fields={"title", "category"})
    rows, stats = load_rows(
        session.connection(),
        Product.__mapper__,
        selection,
        where=Product.__table__.c.source == "test",
    )
    assert len(rows) == 3
    assert stats.queries == 1, stats.per_relationship


def test_one_query_per_relationship_regardless_of_row_count(
    session: Session, seeded: dict[str, int]
) -> None:
    """Three products with five offers between them still cost one query for the
    products and one for the offers."""
    selection = Selection(
        fields={"title"},
        children={
            "brand": Selection(fields={"name"}),
            "offers": Selection(fields={"price_usd_cents"}),
        },
    )
    rows, stats = load_rows(
        session.connection(),
        Product.__mapper__,
        selection,
        where=Product.__table__.c.source == "test",
    )
    assert len(rows) == 3
    # One for products, one for brands, one for offers. Not one per product.
    assert stats.queries == 3, stats.per_relationship
    assert sum(len(row["offers"]) for row in rows) == 5


def test_nested_depth_costs_one_query_per_level(session: Session, seeded: dict[str, int]) -> None:
    selection = Selection(
        fields={"title"},
        children={
            "offers": Selection(
                fields={"price_usd_cents"},
                children={"retailer": Selection(fields={"name"})},
            )
        },
    )
    rows, stats = load_rows(
        session.connection(),
        Product.__mapper__,
        selection,
        where=Product.__table__.c.source == "test",
    )
    # products, offers, retailers.
    assert stats.queries == 3, stats.per_relationship
    retailers = {
        offer["retailer"]["name"] for row in rows for offer in row["offers"] if offer["retailer"]
    }
    assert retailers == {"Net-a-Porter", "SSENSE"}


def test_unselected_relationships_are_not_queried(session: Session, seeded: dict[str, int]) -> None:
    """The selection set drives the plan: an unrequested relationship costs nothing."""
    selection = Selection(fields={"title"})
    _, stats = load_rows(
        session.connection(),
        Product.__mapper__,
        selection,
        where=Product.__table__.c.source == "test",
    )
    assert stats.queries == 1
    assert stats.per_relationship == ["root"]


def test_instantiate_sets_only_selected_fields(session: Session, seeded: dict[str, int]) -> None:
    """A partial selection produces a partial instance, not a fabricated row."""
    selection = Selection(fields={"title"}, children={"brand": Selection(fields={"name"})})
    rows, _ = load_rows(
        session.connection(),
        Product.__mapper__,
        selection,
        where=Product.__table__.c.source == "test",
    )
    instances = instantiate(Product.__mapper__, rows, selection)
    assert len(instances) == 3
    first = instances[0]
    assert first.title.startswith("Test product")
    assert first.brand.name in {"Ganni", "Toteme"}
    # Not selected, so it stays None rather than being invented.
    assert first.description is None
    assert first.category is None


def test_null_foreign_key_yields_none_not_an_empty_object(session: Session) -> None:
    """Null means unknown all the way through: a product with no brand resolves
    to None, never to a blank Brand."""
    orphan = Product(
        source="test-orphan",
        source_id="orphan-1",
        provenance=Provenance.model_extraction,
        brand_id=None,
        title="Unbranded",
    )
    session.add(orphan)
    session.flush()

    selection = Selection(fields={"title"}, children={"brand": Selection(fields={"name"})})
    rows, stats = load_rows(
        session.connection(),
        Product.__mapper__,
        selection,
        where=Product.__table__.c.source == "test-orphan",
    )
    instances = instantiate(Product.__mapper__, rows, selection)
    assert instances[0].brand is None
    # No join values means no second query at all.
    assert stats.queries == 1
