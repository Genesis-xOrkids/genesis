"""Remove catalog products the non-apparel rule now turns away at ingestion.

    PYTHONPATH=. uv run python -m scripts.remove_non_apparel            # counts, removes nothing
    PYTHONPATH=. uv run python -m scripts.remove_non_apparel --apply    # removes them

Ingestion upserts and never deletes, so the towels, bedding and gift cards read
before ``vocabulary.not_apparel`` existed stay in the catalog after it starts
quarantining them. This takes them out, judged by that same function on the title
stored with each product, which is the title the connector judged: the rule reads
nothing else, so a stored row and a fresh record get the same verdict.

Each product goes with its offers. The schema's own ``ON DELETE CASCADE`` takes
their sizes, images, materials and attributes; offers are removed first because
their key to the product declares no cascade. Everything happens in one
transaction, so a run removes all of it or none of it.

The writer has no delete, and the ORM is not used for this one either: every
relationship is ``lazy="raise"`` with no delete cascade declared, so
``session.delete`` would have to load each child just to be told to leave it.

Dry run by default, and safe to repeat: a second run finds nothing. It prints the
database it is pointed at before anything else.
"""

from __future__ import annotations

import argparse
import collections
import sys
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy import Table, delete, select
from sqlalchemy.orm import Session

from api.genesis_api.db import write_session
from api.genesis_api.models import Offer, Product, Retailer
from intelligence.catalog.vocabulary import NonApparelKind, not_apparel

# A product no offer links to has no retailer to count it under.
NO_RETAILER = "(no offer)"


@dataclass
class Removal:
    """What a run found, and whether it removed it."""

    applied: bool
    products: collections.Counter[tuple[str, NonApparelKind]] = field(
        default_factory=collections.Counter
    )
    product_ids: list[int] = field(default_factory=list)
    offers: int = 0


def remove_non_apparel(session: Session, *, apply: bool) -> Removal:
    """Find every product whose title the rule rejects, and remove it when asked."""
    products = cast(Table, Product.__table__)
    offers = cast(Table, Offer.__table__)
    retailers = cast(Table, Retailer.__table__)

    rows = session.execute(
        select(products.c.id, products.c.title, retailers.c.name, offers.c.id.label("offer_id"))
        .outerjoin(offers, offers.c.product_id == products.c.id)
        .outerjoin(retailers, retailers.c.id == offers.c.retailer_id)
        .order_by(products.c.id)
    ).all()

    removal = Removal(applied=apply)
    retailer_names: dict[int, set[str]] = collections.defaultdict(set)
    kinds: dict[int, NonApparelKind] = {}
    for row in rows:
        rejected = not_apparel(row.title)
        if rejected is None:
            continue
        kinds[row.id] = rejected.kind
        if row.offer_id is not None:
            retailer_names[row.id].add(row.name)
            removal.offers += 1

    for product_id, kind in kinds.items():
        retailer = " + ".join(sorted(retailer_names[product_id])) or NO_RETAILER
        removal.products[(retailer, kind)] += 1
    removal.product_ids = list(kinds)

    if apply and removal.product_ids:
        session.execute(delete(offers).where(offers.c.product_id.in_(removal.product_ids)))
        session.execute(delete(products).where(products.c.id.in_(removal.product_ids)))
    return removal


def report(removal: Removal) -> str:
    lines = [f"{'retailer':28s} {'reason':20s} {'products':>8s}"]
    ordered = sorted(removal.products.items(), key=lambda item: (item[0][0], item[0][1].value))
    for (retailer, kind), count in ordered:
        lines.append(f"{retailer:28s} {kind.value:20s} {count:8d}")
    verb = "removed" if removal.applied else "would be removed (dry run; --apply removes them)"
    lines.append(f"{len(removal.product_ids)} products and {removal.offers} offers {verb}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="remove what the dry run counts")
    args = parser.parse_args()

    with write_session() as session:
        url = session.get_bind().engine.url
        print(f"against {url.database} at {url.host}")
        removal = remove_non_apparel(session, apply=args.apply)
    print(report(removal))
    return 0


if __name__ == "__main__":
    sys.exit(main())
