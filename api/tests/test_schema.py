"""End-to-end GraphQL: a real query and a real write against a real database.

These execute through the schema the way a client does, so they cover the parts
unit tests miss - camelCase name mapping, enum serialization, nullability, and
the write door's coercion.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, text

from api.genesis_api.db import engine
from api.genesis_api.graphql.schema import schema
from api.genesis_api.models import Brand, Offer, Product, Retailer


@pytest.fixture
def catalog_fixture():
    """Committed data, because the schema opens its own connections.

    Cleaned up explicitly rather than rolled back: the resolvers do not share the
    test's transaction, so an uncommitted row would be invisible to them.
    """
    with engine().begin() as conn:
        conn.execute(delete(Offer.__table__).where(Offer.__table__.c.source == "gqltest"))
        conn.execute(delete(Product.__table__).where(Product.__table__.c.source == "gqltest"))
        conn.execute(delete(Brand.__table__).where(Brand.__table__.c.slug == "gqltest-brand"))
        conn.execute(
            delete(Retailer.__table__).where(Retailer.__table__.c.slug == "gqltest-retailer")
        )

        brand_id = conn.execute(
            text(
                "insert into brands (slug, name, price_tier) values "
                "('gqltest-brand', 'Test Brand', 'contemporary') returning id"
            )
        ).scalar_one()
        retailer_id = conn.execute(
            text(
                "insert into retailers (slug, name) values "
                "('gqltest-retailer', 'Test Retailer') returning id"
            )
        ).scalar_one()
        product_id = conn.execute(
            text(
                "insert into products (source, source_id, provenance, brand_id, title, "
                "category, color_family, silhouette) values "
                "('gqltest', 'sku-1', 'feed_sync', :b, 'Silk slip dress', 'dress', "
                "'black', 'column') returning id"
            ),
            {"b": brand_id},
        ).scalar_one()
        conn.execute(
            text(
                "insert into offers (source, source_id, provenance, product_id, retailer_id, "
                "url, price_amount_minor, currency, price_usd_cents, in_stock) values "
                "('gqltest', 'o-1', 'feed_sync', :p, :r, 'https://example.test/p', "
                "42000, 'USD', 42000, true)"
            ),
            {"p": product_id, "r": retailer_id},
        )

    yield {"product_id": product_id, "brand_id": brand_id}

    with engine().begin() as conn:
        conn.execute(delete(Offer.__table__).where(Offer.__table__.c.source == "gqltest"))
        conn.execute(delete(Product.__table__).where(Product.__table__.c.source == "gqltest"))
        conn.execute(delete(Brand.__table__).where(Brand.__table__.c.slug == "gqltest-brand"))
        conn.execute(
            delete(Retailer.__table__).where(Retailer.__table__.c.slug == "gqltest-retailer")
        )


def test_query_traverses_relationships_and_maps_camel_case(catalog_fixture) -> None:
    result = schema.execute_sync(
        """
        query($id: Int!) {
          product(id: $id) {
            title
            category
            colorFamily
            brand { name priceTier }
            offers { priceUsdCents currency inStock retailer { name } }
          }
        }
        """,
        variable_values={"id": catalog_fixture["product_id"]},
    )
    assert result.errors is None, result.errors
    product = result.data["product"]
    assert product["title"] == "Silk slip dress"
    assert product["category"] == "dress"
    assert product["colorFamily"] == "black"
    assert product["brand"] == {"name": "Test Brand", "priceTier": "contemporary"}
    assert len(product["offers"]) == 1
    assert product["offers"][0]["priceUsdCents"] == 42000
    assert product["offers"][0]["inStock"] is True
    assert product["offers"][0]["retailer"]["name"] == "Test Retailer"


def test_unselected_fields_are_absent_not_defaulted(catalog_fixture) -> None:
    """A field the client did not ask for is simply not in the response."""
    result = schema.execute_sync(
        "query($id: Int!) { product(id: $id) { title } }",
        variable_values={"id": catalog_fixture["product_id"]},
    )
    assert result.errors is None, result.errors
    assert result.data["product"] == {"title": "Silk slip dress"}


def test_unknown_id_returns_null_rather_than_an_empty_object(catalog_fixture) -> None:
    result = schema.execute_sync(
        "query { product(id: 99999999) { title } }",
    )
    assert result.errors is None, result.errors
    assert result.data["product"] is None


def test_write_data_creates_and_then_updates_through_one_door() -> None:
    # Clean up front as well as after: a previous failed run leaves the row
    # behind, and then this test reads a stale "created: false" and fails for a
    # reason that has nothing to do with the code under test.
    with engine().begin() as conn:
        conn.execute(delete(Brand.__table__).where(Brand.__table__.c.slug == "gqltest-writedoor"))

    created = schema.execute_sync(
        """
        mutation {
          writeData(targets: [{
            entity: "Brand",
            naturalKey: [{name: "slug", value: "gqltest-writedoor"}],
            values: [{name: "name", value: "Write Door"}, {name: "priceTier", value: "luxury"}]
          }]) { entity id created }
        }
        """
    )
    assert created.errors is None, created.errors
    outcome = created.data["writeData"][0]
    assert outcome["entity"] == "Brand"
    assert outcome["created"] is True
    brand_id = outcome["id"]

    updated = schema.execute_sync(
        """
        mutation {
          writeData(targets: [{
            entity: "Brand",
            naturalKey: [{name: "slug", value: "gqltest-writedoor"}],
            values: [{name: "name", value: "Write Door Renamed"}]
          }]) { id created }
        }
        """
    )
    assert updated.errors is None, updated.errors
    assert updated.data["writeData"][0]["id"] == brand_id
    assert updated.data["writeData"][0]["created"] is False

    read_back = schema.execute_sync(
        "query($id: Int!) { brand(id: $id) { name priceTier } }",
        variable_values={"id": brand_id},
    )
    assert read_back.data["brand"]["name"] == "Write Door Renamed"
    assert read_back.data["brand"]["priceTier"] == "luxury", "unwritten field is preserved"

    with engine().begin() as conn:
        conn.execute(delete(Brand.__table__).where(Brand.__table__.c.id == brand_id))


def test_write_rejects_an_invalid_enum_value_rather_than_defaulting() -> None:
    result = schema.execute_sync(
        """
        mutation {
          writeData(targets: [{
            entity: "Brand",
            naturalKey: [{name: "slug", value: "gqltest-badenum"}],
            values: [{name: "priceTier", value: "not_a_tier"}]
          }]) { id }
        }
        """
    )
    assert result.errors, "an invalid enum must raise, not fall back to a default"


def test_write_rejects_an_unknown_entity() -> None:
    result = schema.execute_sync(
        """
        mutation {
          writeData(targets: [{
            entity: "NotAnEntity", naturalKey: [], values: []
          }]) { id }
        }
        """
    )
    assert result.errors
