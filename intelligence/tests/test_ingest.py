"""Connector output into the database, end to end.

These run against real Postgres because the properties under test are database
properties: idempotency on a natural key, foreign keys that actually resolve,
and nulls that survive as unknown rather than becoming zeros.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.genesis_api.models import Brand, IngestionFailure, Offer, OfferSize, Product
from api.genesis_api.models.enums import Category, ColorFamily, SizeSystem
from intelligence.catalog.connectors.affiliate_feed import (
    RAKUTEN_COLUMNS,
    AffiliateFeedConnector,
)
from intelligence.catalog.connectors.base import Connector
from intelligence.catalog.connectors.shopify import ShopifyConnector
from intelligence.catalog.connectors.shopify_public import (
    ShopifyPublicConnector,
    StorefrontProfile,
)
from intelligence.catalog.ingest import ingest, offer_id_for, product_id_for, slugify
from intelligence.catalog.money import FxRates

RATES = FxRates(
    as_of=datetime.datetime(2026, 9, 3, tzinfo=datetime.UTC),
    usd_per_unit={"EUR": Decimal("1.09"), "GBP": Decimal("1.27")},
)


SHOPIFY_RECORDS = [
    {
        "id": "gid://shopify/Product/1",
        "title": "Silk Shirt Dress",
        "vendor": "Ganni",
        "productType": "Dresses",
        "tags": ["womens", "midi", "v-neck"],
        "currencyCode": "EUR",
        "colorHex": "#1a2b5e",
        "onlineStoreUrl": "https://ganni.com/p/1",
        "images": [{"url": "https://cdn/1.jpg", "width": 1200, "height": 1600}],
        "variants": [
            {"title": "EU 36", "price": "295.00", "availableForSale": True},
            {"title": "EU 38", "price": "295.00", "availableForSale": False},
        ],
        "sizeSystem": "eu",
    },
    {
        "id": "gid://shopify/Product/2",
        "title": "Oversized Wool Coat",
        "vendor": "Toteme",
        "productType": "Coats",
        "tags": ["womens"],
        "currencyCode": "EUR",
        "onlineStoreUrl": "https://toteme.com/p/2",
        "variants": [{"title": "S", "price": "890.00", "availableForSale": True}],
    },
]

FEED_ROWS = [
    {
        "sku": "NAP-1",
        "productname": "Toteme High-Rise Wide Leg Jeans",
        "brand": "Toteme",
        "primarycategory": "Womens Denim",
        "price": "290.00",
        "saleprice": "245.00",
        "currency": "GBP",
        "linkurl": "https://nap.com/1",
        "imageurl": "https://i/1.jpg",
        "color": "Indigo",
        "color_hex": "#2c3e6b",
        "size": "XS,S,M",
        "instock": "in stock",
    }
]


def _shopify() -> ShopifyConnector:
    return ShopifyConnector(rates=RATES, store_name="Ganni Store")


def _feed() -> AffiliateFeedConnector:
    return AffiliateFeedConnector(
        source="rakuten-test", retailer_name="Net-a-Porter", rates=RATES, columns=RAKUTEN_COLUMNS
    )


def _public() -> ShopifyPublicConnector:
    profile = StorefrontProfile(
        domain="cozyearth.test", retailer_name="Cozy Earth", currency="USD", brand_name="Cozy Earth"
    )
    return ShopifyPublicConnector(profile=profile, rates=RATES)


def test_a_run_writes_products_offers_images_and_sizes(session: Session) -> None:
    report = ingest(session, _shopify().normalize(SHOPIFY_RECORDS))

    assert report.products_written == 2
    assert report.offers_written == 2
    assert report.images_written == 1
    assert report.sizes_written == 3
    assert report.brands_resolved == 2
    assert report.retailers_resolved == 1
    assert report.quarantined == 0


def test_canonical_values_land_on_the_row(session: Session) -> None:
    ingest(session, _shopify().normalize(SHOPIFY_RECORDS))
    product_id = product_id_for(session, "shopify", "gid://shopify/Product/1")
    assert product_id is not None

    row = session.execute(
        select(
            Product.__table__.c.title,
            Product.__table__.c.category,
            Product.__table__.c.color_hex,
            Product.__table__.c.color_family,
            Product.__table__.c.garment_length,
        ).where(Product.__table__.c.id == product_id)
    ).one()
    assert row.title == "Silk Shirt Dress"
    assert row.category is Category.dress, "shirt dress is a dress, not a shirt"
    assert row.color_hex == "#1a2b5e"
    assert row.color_family is ColorFamily.navy, "family is derived from the hex"


def test_a_currency_price_is_converted_and_the_source_amount_is_kept(
    session: Session,
) -> None:
    """The listed amount and currency are the facts; the USD value is derived and
    carries the rate that produced it."""
    ingest(session, _shopify().normalize(SHOPIFY_RECORDS))
    offer_id = offer_id_for(session, "shopify", "gid://shopify/Product/1@Ganni Store")
    row = session.execute(
        select(
            Offer.__table__.c.price_amount_minor,
            Offer.__table__.c.currency,
            Offer.__table__.c.price_usd_cents,
            Offer.__table__.c.fx_rate_at,
        ).where(Offer.__table__.c.id == offer_id)
    ).one()
    assert row.price_amount_minor == 29500
    assert row.currency == "EUR"
    assert row.price_usd_cents == 32155
    assert row.fx_rate_at is not None, "a derived price without its rate cannot be audited"


def test_reingesting_the_same_feed_does_not_duplicate(session: Session) -> None:
    """The property the whole ingestion design rests on."""
    connector = _shopify()
    ingest(session, connector.normalize(SHOPIFY_RECORDS))
    first = session.execute(
        select(func.count())
        .select_from(Product.__table__)
        .where(Product.__table__.c.source == "shopify")
    ).scalar_one()

    ingest(session, connector.normalize(SHOPIFY_RECORDS))
    second = session.execute(
        select(func.count())
        .select_from(Product.__table__)
        .where(Product.__table__.c.source == "shopify")
    ).scalar_one()

    assert first == second == 2


def test_a_changed_price_updates_in_place(session: Session) -> None:
    connector = _shopify()
    ingest(session, connector.normalize(SHOPIFY_RECORDS))

    marked_down = [dict(record) for record in SHOPIFY_RECORDS]
    marked_down[0] = {
        **marked_down[0],
        "variants": [{"title": "EU 36", "price": "195.00", "availableForSale": True}],
    }
    ingest(session, connector.normalize(marked_down))

    offer_id = offer_id_for(session, "shopify", "gid://shopify/Product/1@Ganni Store")
    price = session.execute(
        select(Offer.__table__.c.price_amount_minor).where(Offer.__table__.c.id == offer_id)
    ).scalar_one()
    assert price == 19500, "the latest write wins"


def test_two_sources_converge_on_one_brand(session: Session) -> None:
    """Toteme arrives from Shopify and from an affiliate feed; it is one brand."""
    ingest(session, _shopify().normalize(SHOPIFY_RECORDS))
    ingest(session, _feed().normalize(FEED_ROWS))

    count = session.execute(
        select(func.count())
        .select_from(Brand.__table__)
        .where(Brand.__table__.c.slug == slugify("Toteme"))
    ).scalar_one()
    assert count == 1


def test_unknown_availability_stays_null_rather_than_false(session: Session) -> None:
    """Null means unknown. A feed that omits availability is not asserting a
    stock-out, and treating it as one would hide half the catalog."""
    rows = [{**FEED_ROWS[0], "sku": "NAP-NOSTOCK", "instock": ""}]
    ingest(session, _feed().normalize(rows))
    offer_id = offer_id_for(session, "rakuten-test", "NAP-NOSTOCK")
    in_stock = session.execute(
        select(Offer.__table__.c.in_stock).where(Offer.__table__.c.id == offer_id)
    ).scalar_one()
    assert in_stock is None


def test_a_sale_price_below_list_is_recorded_and_one_at_list_is_not(
    session: Session,
) -> None:
    """Feeds repeat the list price in the sale column constantly; recording that
    as a markdown would badge the whole catalog as discounted."""
    rows = [
        {**FEED_ROWS[0], "sku": "NAP-SALE", "price": "290.00", "saleprice": "245.00"},
        {**FEED_ROWS[0], "sku": "NAP-NOSALE", "price": "290.00", "saleprice": "290.00"},
    ]
    ingest(session, _feed().normalize(rows))
    with_sale = session.execute(
        select(Offer.__table__.c.sale_price_amount_minor).where(
            Offer.__table__.c.source_id == "NAP-SALE"
        )
    ).scalar_one()
    without = session.execute(
        select(Offer.__table__.c.sale_price_amount_minor).where(
            Offer.__table__.c.source_id == "NAP-NOSALE"
        )
    ).scalar_one()
    assert with_sale == 24500
    assert without is None


def test_bad_records_are_quarantined_with_their_payload(session: Session) -> None:
    """A record that fails validation is kept with its error, not dropped."""
    rows = [
        {"sku": "", "productname": "no id"},
        {"sku": "NAP-NOPRICE", "productname": "Missing Price", "currency": "GBP"},
    ]
    report = ingest(session, _feed().normalize(rows))
    assert report.quarantined == 2
    assert report.products_written == 0

    failures = session.execute(
        select(IngestionFailure.__table__.c.stage, IngestionFailure.__table__.c.error).where(
            IngestionFailure.__table__.c.source == "rakuten-test"
        )
    ).all()
    stages = {row.stage for row in failures}
    assert stages == {"identify", "normalize"}
    assert any("no price" in row.error for row in failures)


@pytest.mark.parametrize(
    ("connector", "towel", "robe"),
    [
        (
            _shopify,
            {**SHOPIFY_RECORDS[1], "id": "gid://shopify/Product/9", "title": "Luxe Bath Towels"},
            {**SHOPIFY_RECORDS[1], "id": "gid://shopify/Product/10", "title": "Luxe Bath Robe"},
        ),
        (
            _feed,
            {**FEED_ROWS[0], "sku": "NAP-9", "productname": "Luxe Bath Towels"},
            {**FEED_ROWS[0], "sku": "NAP-10", "productname": "Luxe Bath Robe"},
        ),
        (
            _public,
            {
                "id": 9,
                "title": "Luxe Bath Towels",
                "handle": "towels",
                "variants": [{"title": "Default Title", "price": "88.00", "available": True}],
            },
            {
                "id": 10,
                "title": "Luxe Bath Robe",
                "handle": "robe",
                "variants": [{"title": "M", "price": "148.00", "available": True}],
            },
        ),
    ],
    ids=["shopify", "affiliate_feed", "shopify_public"],
)
def test_every_connector_quarantines_what_is_not_apparel(
    session: Session,
    connector: Callable[[], Connector],
    towel: dict[str, object],
    robe: dict[str, object],
) -> None:
    """The rule lives at the boundary, so no source can ingest a towel and no
    source can turn away a bath robe."""
    source = connector()
    report = ingest(session, source.normalize([towel, robe]))

    assert report.quarantined == 1
    assert report.products_written == 1
    failure = session.execute(
        select(IngestionFailure.__table__.c.stage, IngestionFailure.__table__.c.error).where(
            IngestionFailure.__table__.c.source == source.source
        )
    ).one()
    assert failure.stage == "filter"
    assert failure.error == "not_apparel: home_goods (towel)"
    category = session.execute(
        select(Product.__table__.c.category).where(Product.__table__.c.source == source.source)
    ).scalar_one()
    assert category is Category.sleepwear


def test_per_size_availability_survives_ingestion(session: Session) -> None:
    ingest(session, _shopify().normalize(SHOPIFY_RECORDS))
    offer_id = offer_id_for(session, "shopify", "gid://shopify/Product/1@Ganni Store")
    sizes = session.execute(
        select(OfferSize.__table__.c.size_value, OfferSize.__table__.c.in_stock)
        .where(OfferSize.__table__.c.offer_id == offer_id)
        .order_by(OfferSize.__table__.c.size_value)
    ).all()
    assert [(row.size_value, row.in_stock) for row in sizes] == [("36", True), ("38", False)]


def test_size_system_is_recorded_not_guessed(session: Session) -> None:
    ingest(session, _shopify().normalize(SHOPIFY_RECORDS))
    offer_id = offer_id_for(session, "shopify", "gid://shopify/Product/1@Ganni Store")
    systems = (
        session.execute(
            select(OfferSize.__table__.c.size_system).where(
                OfferSize.__table__.c.offer_id == offer_id
            )
        )
        .scalars()
        .all()
    )
    assert set(systems) == {SizeSystem.eu}


def test_both_connectors_produce_the_same_canonical_shape(session: Session) -> None:
    """The boundary's whole claim: two sources with nothing structurally in
    common land on identical row shapes."""
    ingest(session, _shopify().normalize(SHOPIFY_RECORDS))
    ingest(session, _feed().normalize(FEED_ROWS))

    rows = session.execute(
        select(Product.__table__.c.source, Product.__table__.c.category).where(
            Product.__table__.c.source.in_(["shopify", "rakuten-test"])
        )
    ).all()
    by_source = {row.source for row in rows}
    assert by_source == {"shopify", "rakuten-test"}
    assert all(row.category is not None for row in rows)


def _sizes_of(session: Session, offer_id: int | None) -> dict[tuple[SizeSystem, str], bool | None]:
    table = OfferSize.__table__
    rows = session.execute(
        select(table.c.size_system, table.c.size_value, table.c.in_stock).where(
            table.c.offer_id == offer_id
        )
    ).all()
    return {(row.size_system, row.size_value): row.in_stock for row in rows}


def test_a_size_the_source_stops_stating_is_retired(session: Session) -> None:
    """The writer upserts, so without retirement a size read once stays forever,
    frozen at its last stock, and a size filter keeps matching it."""
    connector = _feed()
    ingest(session, connector.normalize(FEED_ROWS))
    offer_id = offer_id_for(session, "rakuten-test", "NAP-1")
    assert set(_sizes_of(session, offer_id)) == {
        (SizeSystem.alpha, "XS"),
        (SizeSystem.alpha, "S"),
        (SizeSystem.alpha, "M"),
    }

    report = ingest(session, connector.normalize([{**FEED_ROWS[0], "size": "S,M"}]))

    assert set(_sizes_of(session, offer_id)) == {(SizeSystem.alpha, "S"), (SizeSystem.alpha, "M")}
    assert report.sizes_retired == 1


def test_an_offer_whose_sizes_are_no_longer_read_keeps_none(session: Session) -> None:
    """Unknown is no row. An offer the source now states no readable size for
    carries no size, not the last one it was read with."""
    connector = _feed()
    ingest(session, connector.normalize(FEED_ROWS))
    offer_id = offer_id_for(session, "rakuten-test", "NAP-1")

    ingest(session, connector.normalize([{**FEED_ROWS[0], "size": "please select"}]))

    assert _sizes_of(session, offer_id) == {}


def test_retiring_sizes_touches_only_the_offers_in_the_run(session: Session) -> None:
    ingest(session, _shopify().normalize(SHOPIFY_RECORDS))
    other_offer_id = offer_id_for(session, "shopify", "gid://shopify/Product/1@Ganni Store")
    before = _sizes_of(session, other_offer_id)

    connector = _feed()
    ingest(session, connector.normalize(FEED_ROWS))
    ingest(session, connector.normalize([{**FEED_ROWS[0], "size": "S"}]))

    assert before
    assert _sizes_of(session, other_offer_id) == before


def test_a_second_identical_run_retires_nothing(session: Session) -> None:
    connector = _feed()
    ingest(session, connector.normalize(FEED_ROWS))
    offer_id = offer_id_for(session, "rakuten-test", "NAP-1")
    first = _sizes_of(session, offer_id)

    report = ingest(session, connector.normalize(FEED_ROWS))

    assert report.sizes_retired == 0
    assert _sizes_of(session, offer_id) == first
