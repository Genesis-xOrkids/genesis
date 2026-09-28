"""Removing products the non-apparel rule rejects, against the test database.

The seed is a catalog as it stood before the rule: towels, a pillowcase, a
loyalty reward and a gift card ingested as products beside the clothing, the way
Cozy Earth's and Alo Yoga's feeds put them there. Every test empties the catalog
first, because the script reads every product and a row another test committed
would land in its counts.
"""

from __future__ import annotations

import collections

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from api.genesis_api.models import Brand, Offer, OfferSize, Product, ProductImage, Retailer
from api.genesis_api.models.enums import Provenance, SizeSystem
from intelligence.catalog.vocabulary import NonApparelKind
from scripts import remove_non_apparel

SOURCE = "remove-non-apparel-test"

# Each product: its source id, its title, the retailer selling it, and how many offers it has.
SEED = (
    ("towels", "Luxe Bath Towels", "cozy", 1),
    ("pillowcases", "Bamboo Pillowcases", "cozy", 2),
    ("reward", "Alo Access Reward", "alo", 1),
    ("gift-box", "Cozy Earth Gift Box", "cozy", 1),
    ("gift-card", "Digital Gift Card", None, 0),
    ("robe", "Luxe Bath Robe", "cozy", 1),
    ("bras", "The Classic All You Bra Trio Bundle", "alo", 1),
    ("point", "The Point II", "cozy", 1),
)
REJECTED = {"towels", "pillowcases", "reward", "gift-box", "gift-card"}


@pytest.fixture
def catalog(session: Session) -> Session:
    session.execute(delete(Offer))
    session.execute(delete(Product))

    brand = Brand(slug="remove-non-apparel-test", name="Remove Non Apparel Test")
    retailers = {
        "cozy": Retailer(slug="cozy-earth-remove-test", name="Cozy Earth"),
        "alo": Retailer(slug="alo-yoga-remove-test", name="Alo Yoga"),
    }
    session.add_all([brand, *retailers.values()])
    session.flush()

    for source_id, title, retailer, offer_count in SEED:
        product = Product(
            source=SOURCE,
            source_id=source_id,
            provenance=Provenance.feed_sync,
            brand_id=brand.id,
            title=title,
        )
        session.add(product)
        session.flush()
        session.add(
            ProductImage(product_id=product.id, position=0, s3_key=f"pending/{source_id}/0")
        )
        for index in range(offer_count):
            assert retailer is not None
            offer = Offer(
                source=SOURCE,
                source_id=f"{source_id}-{index}",
                provenance=Provenance.feed_sync,
                product_id=product.id,
                retailer_id=retailers[retailer].id,
                url="https://example.test/p",
                price_amount_minor=8800,
                currency="USD",
            )
            session.add(offer)
            session.flush()
            session.add(OfferSize(offer_id=offer.id, size_system=SizeSystem.alpha, size_value="M"))
    session.flush()
    return session


def _count(session: Session, model: type[Offer | OfferSize | ProductImage]) -> int:
    return int(session.execute(select(func.count()).select_from(model)).scalar_one())


def _remaining(session: Session) -> set[str]:
    return set(
        session.execute(
            select(Product.__table__.c.source_id).where(Product.__table__.c.source == SOURCE)
        ).scalars()
    )


def test_a_dry_run_counts_by_retailer_and_reason_and_removes_nothing(catalog: Session) -> None:
    removal = remove_non_apparel.remove_non_apparel(catalog, apply=False)

    assert removal.products == collections.Counter(
        {
            ("Cozy Earth", NonApparelKind.home_goods): 2,
            ("Cozy Earth", NonApparelKind.gift_or_service): 1,
            ("Alo Yoga", NonApparelKind.loyalty_reward): 1,
            (remove_non_apparel.NO_RETAILER, NonApparelKind.gift_or_service): 1,
        }
    )
    assert removal.offers == 5
    assert _remaining(catalog) == {source_id for source_id, *_ in SEED}
    assert _count(catalog, Offer) == 8
    # One retailer under two reasons is a row each, in a stable order.
    assert remove_non_apparel.report(removal).splitlines()[1:4] == [
        f"{'(no offer)':28s} {'gift_or_service':20s} {1:8d}",
        f"{'Alo Yoga':28s} {'loyalty_reward':20s} {1:8d}",
        f"{'Cozy Earth':28s} {'gift_or_service':20s} {1:8d}",
    ]
    assert "would be removed (dry run" in remove_non_apparel.report(removal)


def test_applying_removes_the_products_with_everything_that_hangs_off_them(
    catalog: Session,
) -> None:
    rejected_ids = set(
        catalog.execute(
            select(Product.__table__.c.id).where(
                Product.__table__.c.source == SOURCE,
                Product.__table__.c.source_id.in_(REJECTED),
            )
        ).scalars()
    )

    removal = remove_non_apparel.remove_non_apparel(catalog, apply=True)

    assert set(removal.product_ids) == rejected_ids
    assert _remaining(catalog) == {"robe", "bras", "point"}
    # Three kept products, three offers, one size each, one image each: nothing
    # of the removed products is left behind, and nothing of the kept ones went.
    assert _count(catalog, Offer) == 3
    assert _count(catalog, OfferSize) == 3
    assert _count(catalog, ProductImage) == 3
    assert remove_non_apparel.report(removal).endswith("5 products and 5 offers removed")


def test_a_second_run_finds_nothing(catalog: Session) -> None:
    remove_non_apparel.remove_non_apparel(catalog, apply=True)

    again = remove_non_apparel.remove_non_apparel(catalog, apply=True)

    assert again.product_ids == []
    assert again.offers == 0
    assert _remaining(catalog) == {"robe", "bras", "point"}
