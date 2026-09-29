"""Catalog ingestion: connector output into the database.

Every insert and update here goes through the one write door. There is no
bespoke INSERT for products, no second path for offers, and no per-source
column: a connector's output becomes write specs, and the writer upserts them on
their natural keys. That is what makes a re-sync idempotent rather than
duplicating the catalog.

Two statements do not, both deletes, because the writer only upserts. The
first is in :func:`_retire_sizes`: an offer's sizes are a set the source
restates in full each run, so the sizes it stopped stating are removed beside
the writer. The second is in :func:`_remove_rejected`: a record the connector
now turns away as not apparel may have been written by a run before the rule
existed, and upserting never takes it back out. Both are scoped to what this
run's source wrote and to rows the feed itself wrote, so neither can reach a
row a person or an agent wrote.

Failures are quarantined, never dropped. A run reports what it wrote and what it
could not read, so a source changing shape shows up as a number instead of as a
catalog that quietly stopped growing.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from typing import cast

import structlog
from sqlalchemy import ARRAY, Integer, Table, Text, any_, delete, exists, func, literal, select
from sqlalchemy.orm import Session

from api.genesis_api.models import Offer, OfferSize, Product
from api.genesis_api.models.enums import Provenance
from api.genesis_api.writer import WriteSpec, write
from intelligence.catalog.normalized import (
    FILTER_STAGE,
    NormalizationResult,
    NormalizedOffer,
    NormalizedProduct,
)

log = structlog.get_logger(__name__)

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """A stable natural key for a brand or retailer name.

    Brands are matched by slug across sources, so "Net-a-Porter", "NET-A-PORTER"
    and "net a porter" have to converge. Without that, one retailer becomes three
    rows and every offer count is wrong.
    """
    slug = _SLUG_PATTERN.sub("-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"name {name!r} has no slug-able characters")
    return slug


@dataclass
class IngestReport:
    """What one run did. Every number here counts rows actually written, except
    ``sizes_retired`` and ``products_removed``, which count rows deleted.

    ``quarantined`` and ``filtered`` are both records put in quarantine, and
    they mean opposite things. A quarantined record could not be read, and a
    rising count is a source changing shape. A filtered one was read and turned
    away as not apparel, which a storefront selling bedding does by design.
    """

    products_written: int = 0
    offers_written: int = 0
    images_written: int = 0
    sizes_written: int = 0
    sizes_retired: int = 0
    products_removed: int = 0
    brands_resolved: int = 0
    retailers_resolved: int = 0
    quarantined: int = 0
    filtered: int = 0
    unresolved_offers: list[str] = field(default_factory=list)


def ingest(session: Session, result: NormalizationResult) -> IngestReport:
    """Write one connector run's output.

    Ordered deliberately: brands and retailers first because products and offers
    reference them, then products, then offers once product ids exist. The writer
    does not reorder specs, so the ordering is stated here rather than inferred.

    Each offer's ``sizes`` must be its complete set: the stored sizes of every
    offer written here are replaced by it, and a size it omits is deleted. A
    caller that updates an offer without knowing its sizes (a price or stock
    recheck) must not come through here.

    Records the connector turned away as not apparel are removed from the
    catalog here too, with whatever earlier runs wrote for them.
    """
    report = IngestReport()

    _write_failures(session, result, report)
    _remove_rejected(session, result, report)
    brand_ids = _resolve_brands(session, result.products, report)
    retailer_ids = _resolve_retailers(session, result.offers, report)

    product_ids = _write_products(session, result.products, brand_ids, report)
    _write_images(session, result.products, product_ids, report)
    _write_offers(session, result.offers, product_ids, retailer_ids, report)

    return report


def _write_failures(session: Session, result: NormalizationResult, report: IngestReport) -> None:
    specs = [
        WriteSpec(
            entity="IngestionFailure",
            natural_key={"source": record.source, "source_id": record.source_id or "(missing)"},
            values={"stage": stage, "error": error, "payload": record.payload},
        )
        for record, stage, error in result.failures
    ]
    if specs:
        write(session, specs)
    report.filtered = sum(1 for _, stage, _ in result.failures if stage == FILTER_STAGE)
    report.quarantined = len(specs) - report.filtered


def _remove_rejected(session: Session, result: NormalizationResult, report: IngestReport) -> None:
    """Delete the products a rejected record produced in earlier runs.

    A product belongs to a record when its ``source_id`` is the record's id or
    starts with it and a colon, the form ``NormalizedProduct`` documents for a
    record split into colourways. Only products the feed wrote are touched
    (``provenance = feed_sync``), and not one that carries an offer anything
    else wrote, so nothing a person or an agent recorded is ever deleted.

    Offers go first, because ``fk_offers_product_id`` declares no ``ON DELETE``;
    the schema's cascades take sizes, images, materials and attributes. Each
    removal is logged with its title and the phrase that rejected it, per
    source, so a false positive is readable in the run's log rather than only
    as a product that went missing.
    """
    by_source: dict[str, list[str]] = collections.defaultdict(list)
    for record, stage, _ in result.failures:
        if stage == FILTER_STAGE:
            by_source[record.source].append(record.source_id)
    products = cast(Table, Product.__table__)
    offers = cast(Table, Offer.__table__)
    for source, record_ids in by_source.items():
        prefixes = [_like_escaped(record_id) + ":%" for record_id in record_ids]
        doomed = session.execute(
            select(products.c.id, products.c.source_id, products.c.title).where(
                products.c.source == source,
                products.c.provenance == Provenance.feed_sync,
                (products.c.source_id == any_(literal(record_ids, ARRAY(Text))))
                | products.c.source_id.like(any_(literal(prefixes, ARRAY(Text)))),
                ~exists().where(
                    offers.c.product_id == products.c.id,
                    offers.c.provenance != Provenance.feed_sync,
                ),
            )
        ).all()
        if not doomed:
            continue
        product_ids = [row.id for row in doomed]
        removed_offers = session.execute(
            delete(offers)
            .where(offers.c.product_id == any_(literal(product_ids, ARRAY(Integer))))
            .returning(offers.c.id)
        )
        offer_count = len(removed_offers.all())
        session.execute(
            delete(products).where(products.c.id == any_(literal(product_ids, ARRAY(Integer))))
        )
        report.products_removed += len(product_ids)
        phrases = collections.Counter(
            result.rejected[
                row.source_id
                if row.source_id in result.rejected
                else row.source_id.rsplit(":", 1)[0]
            ].phrase
            for row in doomed
        )
        log.info(
            "non_apparel_removed",
            source=source,
            products=len(product_ids),
            offers=offer_count,
            by_phrase=dict(phrases.most_common()),
            titles=sorted({row.title for row in doomed}),
        )


def _like_escaped(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _resolve_brands(
    session: Session, products: list[NormalizedProduct], report: IngestReport
) -> dict[str, int]:
    names = {p.brand_name for p in products if p.brand_name}
    if not names:
        return {}
    specs = [
        WriteSpec(entity="Brand", natural_key={"slug": slugify(name)}, values={"name": name})
        for name in sorted(names)
    ]
    results = write(session, specs)
    report.brands_resolved = len(results)
    return {
        spec.natural_key["slug"]: outcome.id for spec, outcome in zip(specs, results, strict=True)
    }


def _resolve_retailers(
    session: Session, offers: list[NormalizedOffer], report: IngestReport
) -> dict[str, int]:
    names = {o.retailer_name for o in offers if o.retailer_name}
    if not names:
        return {}
    specs = [
        WriteSpec(entity="Retailer", natural_key={"slug": slugify(name)}, values={"name": name})
        for name in sorted(names)
    ]
    results = write(session, specs)
    report.retailers_resolved = len(results)
    return {
        spec.natural_key["slug"]: outcome.id for spec, outcome in zip(specs, results, strict=True)
    }


def _write_products(
    session: Session,
    products: list[NormalizedProduct],
    brand_ids: dict[str, int],
    report: IngestReport,
) -> dict[str, int]:
    if not products:
        return {}
    specs = []
    for product in products:
        values: dict[str, object] = {
            "provenance": Provenance.feed_sync,
            "title": product.title,
            "description": product.description,
            "category": product.category,
            "gender": product.gender,
            "silhouette": product.silhouette,
            "neckline": product.neckline,
            "sleeve_length": product.sleeve_length,
            "sleeve_style": product.sleeve_style,
            "garment_length": product.garment_length,
            "rise": product.rise,
            "fit": product.fit,
            "pattern": product.pattern,
            "color_hex": product.color_hex,
            "color_family": product.color_family,
        }
        if product.brand_name:
            values["brand_id"] = brand_ids[slugify(product.brand_name)]
        specs.append(
            WriteSpec(
                entity="Product",
                natural_key={"source": product.source, "source_id": product.source_id},
                values=values,
            )
        )
    results = write(session, specs)
    report.products_written = len(results)
    return {
        product.source_id: outcome.id for product, outcome in zip(products, results, strict=True)
    }


def _write_images(
    session: Session,
    products: list[NormalizedProduct],
    product_ids: dict[str, int],
    report: IngestReport,
) -> None:
    specs = [
        WriteSpec(
            entity="ProductImage",
            natural_key={
                "product_id": product_ids[product.source_id],
                "position": image.position,
            },
            values={
                # The connector hands us the source URL. The bytes are copied to
                # our own storage by a later step; until then the key mirrors the
                # source so the row is never written without one.
                "s3_key": f"pending/{product.source}/{product.source_id}/{image.position}",
                "source_url": image.source_url,
                "width_px": image.width_px,
                "height_px": image.height_px,
            },
        )
        for product in products
        for image in product.images
    ]
    if specs:
        write(session, specs)
    report.images_written = len(specs)


def _write_offers(
    session: Session,
    offers: list[NormalizedOffer],
    product_ids: dict[str, int],
    retailer_ids: dict[str, int],
    report: IngestReport,
) -> None:
    specs = []
    writable: list[NormalizedOffer] = []
    for offer in offers:
        product_id = product_ids.get(offer.product_source_id)
        if product_id is None:
            # An offer whose product failed normalization has nothing to attach
            # to. Recorded rather than dropped, because a rising count here means
            # the product side of a feed is breaking.
            report.unresolved_offers.append(offer.source_id)
            continue
        writable.append(offer)
        specs.append(
            WriteSpec(
                entity="Offer",
                natural_key={"source": offer.source, "source_id": offer.source_id},
                values={
                    "provenance": Provenance.feed_sync,
                    "product_id": product_id,
                    "retailer_id": retailer_ids[slugify(offer.retailer_name)],
                    "url": offer.url,
                    "affiliate_url": offer.affiliate_url,
                    "price_amount_minor": offer.price_amount_minor,
                    "currency": offer.currency,
                    "sale_price_amount_minor": offer.sale_price_amount_minor,
                    "price_usd_cents": offer.price_usd_cents,
                    "fx_rate_at": offer.fx_rate_at,
                    "in_stock": offer.in_stock,
                },
            )
        )
    if not specs:
        return
    results = write(session, specs)
    report.offers_written = len(results)

    size_specs = [
        WriteSpec(
            entity="OfferSize",
            natural_key={
                "offer_id": outcome.id,
                "size_system": size.system,
                "size_value": size.value,
            },
            values={"in_stock": size.in_stock},
        )
        for offer, outcome in zip(writable, results, strict=True)
        for size in offer.sizes
    ]
    size_results = write(session, size_specs) if size_specs else []
    report.sizes_written = len(size_specs)
    report.sizes_retired = _retire_sizes(
        session,
        offer_ids=[outcome.id for outcome in results],
        kept_size_ids=[outcome.id for outcome in size_results],
    )


def _retire_sizes(session: Session, *, offer_ids: list[int], kept_size_ids: list[int]) -> int:
    """Delete the size rows of offers this run wrote that this run did not write.

    The writer upserts, so it adds and updates sizes but never removes one. A
    size the source stopped listing, or one an earlier connector read wrongly
    ("29" as US 29 before it was read as the waist of 29x32), would otherwise
    keep its last stock forever beside the current reading, and a size filter
    would go on matching it. The offer's sizes are the latest run's, entire.

    Scoped to the offers written here, so a run over one storefront never
    touches another's rows, and idempotent: a second run retires nothing.
    Arrays keep it one statement at any size, where an IN list would pass
    Postgres' bind-parameter limit on a large storefront. The kept ids go
    through a subquery rather than ``<> ALL``, because Postgres hashes the
    first and compares every pair in the second: 13 ms against 3.7 s for 40,000
    rows on the local database.
    """
    table = cast(Table, OfferSize.__table__)
    retired = session.execute(
        delete(table)
        .where(
            table.c.offer_id == any_(literal(offer_ids, ARRAY(Integer))),
            table.c.id.not_in(select(func.unnest(literal(kept_size_ids, ARRAY(Integer))))),
        )
        .returning(table.c.id)
    )
    return len(retired.all())


def product_id_for(session: Session, source: str, source_id: str) -> int | None:
    """Look up a product by its natural key, for callers that need the id later."""
    return session.execute(
        select(Product.__table__.c.id).where(
            Product.__table__.c.source == source,
            Product.__table__.c.source_id == source_id,
        )
    ).scalar_one_or_none()


def offer_id_for(session: Session, source: str, source_id: str) -> int | None:
    return session.execute(
        select(Offer.__table__.c.id).where(
            Offer.__table__.c.source == source,
            Offer.__table__.c.source_id == source_id,
        )
    ).scalar_one_or_none()
