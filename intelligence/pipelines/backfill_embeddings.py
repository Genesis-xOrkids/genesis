"""Embed the catalog so search can match on meaning rather than words.

Products are embedded from their primary photograph, because the model is
contrastive: image and description were trained to land at the same point, and
querying that space with text is the objective it was trained on. Where an image
cannot be fetched the product falls back to its text, which still works and is
simply weaker.

The job is incremental and re-runnable. Only products with no embedding are
considered, so a run that dies partway resumes rather than restarting, and a
nightly pass costs nothing once the catalog is caught up.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, cast

import httpx2
import structlog
from sqlalchemy import Table, bindparam, select, text, update
from sqlalchemy.orm import Session

from api.genesis_api.models import Brand, Product, ProductImage
from services.embeddings import FashionEmbedder, product_document

log = structlog.get_logger(__name__)

USER_AGENT = "genesis-catalog/0.1 (+https://genesis.example/crawler)"
# Product images live on a content delivery network built for exactly this, not
# on a merchant's own server, so a modest amount of concurrency is appropriate
# where it would not be against a storefront.
IMAGE_CONCURRENCY = 16
IMAGE_TIMEOUT_SECONDS = 20.0
# Beyond this a "product image" is something else - a size chart, a lookbook PDF
# render - and decoding it wastes more time than skipping it.
MAX_IMAGE_BYTES = 12_000_000
# The model sees 224 pixels. Full-resolution product photography averages over
# two megabytes, so downloading it to immediately throw away 97% of the pixels
# made fetching the slowest part of the job. Shopify's CDN resizes on request;
# 384 leaves headroom for the preprocessing crop without paying for the rest.
IMAGE_WIDTH = 384
_RESIZABLE_HOSTS = ("cdn.shopify.com",)


def sized_image_url(url: str) -> str:
    """Ask the CDN for an image near the size the model actually needs.

    Only for hosts known to support it. Appending an unrecognised parameter
    elsewhere is at best ignored and at worst breaks a signed URL.
    """
    if not any(host in url for host in _RESIZABLE_HOSTS):
        return url
    if "width=" in url:
        return url
    return f"{url}{'&' if '?' in url else '?'}width={IMAGE_WIDTH}"


@dataclass
class BackfillReport:
    considered: int = 0
    embedded_from_image: int = 0
    embedded_from_text: int = 0
    image_fetch_failed: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def embedded(self) -> int:
        return self.embedded_from_image + self.embedded_from_text


@dataclass(frozen=True)
class Candidate:
    """A product needing an embedding, with everything needed to make one."""

    id: int
    title: str
    brand: str | None
    category: str | None
    color: str | None
    silhouette: str | None
    pattern: str | None
    description: str | None
    image_url: str | None


def candidates(session: Session, *, limit: int) -> list[Candidate]:
    """Products with no embedding, each with its primary image.

    The image is chosen by position rather than arbitrarily: merchandisers put
    the front-facing product shot first, and embedding a detail crop of a cuff
    would describe the cuff.
    """
    products = Product.__table__
    images = ProductImage.__table__
    brands = Brand.__table__

    primary = (
        select(images.c.product_id, images.c.source_url)
        .distinct(images.c.product_id)
        .order_by(images.c.product_id, images.c.position)
        .subquery()
    )
    statement = (
        select(
            products.c.id,
            products.c.title,
            brands.c.name.label("brand"),
            products.c.category,
            products.c.color_family,
            products.c.silhouette,
            products.c.pattern,
            products.c.description,
            primary.c.source_url.label("image_url"),
        )
        .select_from(products)
        .outerjoin(brands, brands.c.id == products.c.brand_id)
        .outerjoin(primary, primary.c.product_id == products.c.id)
        .where(products.c.embedding.is_(None))
        .order_by(products.c.id)
        .limit(limit)
    )
    return [
        Candidate(
            id=row["id"],
            title=row["title"],
            brand=row["brand"],
            category=row["category"].value if row["category"] else None,
            color=row["color_family"].value if row["color_family"] else None,
            silhouette=row["silhouette"].value if row["silhouette"] else None,
            pattern=row["pattern"].value if row["pattern"] else None,
            description=row["description"],
            image_url=row["image_url"],
        )
        for row in session.execute(statement).mappings()
    ]


def fetch_images(urls: list[str | None]) -> list[bytes | None]:
    """Fetch product images concurrently, returning None for any that fail.

    A failed image is not a failed product: it falls back to text. Failing the
    whole batch for one bad URL would make a backfill of this size unfinishable.
    """
    results: list[bytes | None] = [None] * len(urls)
    wanted = [(index, url) for index, url in enumerate(urls) if url]
    if not wanted:
        return results

    with httpx2.Client(
        timeout=IMAGE_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:

        def fetch(item: tuple[int, str]) -> tuple[int, bytes | None]:
            index, url = item
            try:
                response = client.get(sized_image_url(url))
            except httpx2.HTTPError:
                return index, None
            if response.status_code != 200:
                return index, None
            content = response.content
            if not content or len(content) > MAX_IMAGE_BYTES:
                return index, None
            return index, content

        with concurrent.futures.ThreadPoolExecutor(max_workers=IMAGE_CONCURRENCY) as pool:
            for index, content in pool.map(fetch, wanted):
                results[index] = content
    return results


def _write_embeddings(session: Session, rows: list[dict[str, Any]]) -> None:
    """Write a batch of vectors in one statement.

    An UPDATE per product would be one network round trip per row, which is the
    same mistake the catalog writer already had to unlearn.
    """
    if not rows:
        return
    statement = (
        update(cast(Table, Product.__table__))
        .where(Product.__table__.c.id == bindparam("product_id"))
        .values(embedding=bindparam("vector"))
    )
    session.execute(statement, rows)


def backfill(
    session: Session,
    embedder: FashionEmbedder,
    *,
    batch_size: int = 128,
    limit: int = 100_000,
) -> BackfillReport:
    """Embed products that have no embedding yet."""
    report = BackfillReport()
    remaining = limit

    while remaining > 0:
        batch = candidates(session, limit=min(batch_size, remaining))
        if not batch:
            break
        remaining -= len(batch)
        report.considered += len(batch)

        images = fetch_images([candidate.image_url for candidate in batch])
        vectors = embedder.embed_images([raw for raw in images if raw is not None])

        # Re-align: embed_images was given only the successful fetches.
        by_position: dict[int, list[float] | None] = {}
        cursor = 0
        for index, raw in enumerate(images):
            if raw is None:
                by_position[index] = None
                continue
            by_position[index] = vectors[cursor]
            cursor += 1

        rows: list[dict[str, Any]] = []
        text_fallbacks: list[tuple[int, str]] = []
        for index, candidate in enumerate(batch):
            vector = by_position.get(index)
            if vector is not None:
                rows.append({"product_id": candidate.id, "vector": vector})
                report.embedded_from_image += 1
                continue
            report.image_fetch_failed += 1
            text_fallbacks.append(
                (
                    candidate.id,
                    product_document(
                        title=candidate.title,
                        brand=candidate.brand,
                        category=candidate.category,
                        color=candidate.color,
                        silhouette=candidate.silhouette,
                        pattern=candidate.pattern,
                        description=candidate.description,
                    ),
                )
            )

        if text_fallbacks:
            fallback_vectors = embedder.embed_texts([doc for _, doc in text_fallbacks])
            for (product_id, _), vector in zip(text_fallbacks, fallback_vectors, strict=True):
                rows.append({"product_id": product_id, "vector": vector})
                report.embedded_from_text += 1

        _write_embeddings(session, rows)
        session.commit()
        log.info(
            "embedding_batch",
            considered=report.considered,
            from_image=report.embedded_from_image,
            from_text=report.embedded_from_text,
        )

    return report


def outstanding(session: Session) -> int:
    """How many products still have no embedding."""
    return int(
        session.execute(text("select count(*) from products where embedding is null")).scalar_one()
    )
