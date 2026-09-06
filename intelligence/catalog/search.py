"""Hybrid catalog search - the one retrieval path both agents call.

Three rankers over the same filtered candidate set:

- **Vector** similarity on fashion-tuned embeddings, which is what finds "quiet
  luxury column dress" when the words never appear in the copy.
- **Lexical** full-text ranking, which is what finds a brand or a fabric named
  exactly.
- **Structured** filters, which are not a ranker at all but a hard gate: a
  budget or a size that is out of stock is a constraint, not a preference.

Rankings are fused with Reciprocal Rank Fusion rather than by adding scores.
Cosine distance and ts_rank are on incompatible scales, and any weighted sum of
them silently encodes a tuning constant nobody measured; RRF only reads
positions, so it needs no normalization.

Results come back as compact rows. Raw retailer HTML never reaches a model:
descriptions are untrusted text, and a product page is a place instructions get
smuggled in.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.engine import Connection

from api.genesis_api.models import Brand, Offer, OfferSize, Product, ProductImage, Retailer
from api.genesis_api.models.enums import Category, ColorFamily, SizeSystem

# The conventional RRF damping constant. Large enough that the top few positions
# of any one ranker cannot dominate the fusion on their own.
RRF_K = 60

# Merchandisers append the colourway to the title after a pipe or a spaced dash.
_TITLE_SEPARATOR = re.compile(r"\s+[|\u2013\u2014-]\s+|\|")

# How deep each ranker goes before fusion. Deeper than the final limit so a
# result ranked poorly by one ranker can still be rescued by another, and deep
# enough that collapsing colourways afterwards still leaves a full page.
CANDIDATE_DEPTH = 200

# At most this many colourways of one style in a result set. Splitting source
# records per colourway is what gave the catalog colour at all, but it means one
# shoe can exist as forty-nine products. Eight results that are the same shoe in
# eight colours is not a result set, and no amount of ranking quality fixes it.
MAX_PER_STYLE = 2


class Embedder(Protocol):
    """Turns a query into a vector in the catalog's embedding space.

    A protocol so search can be built and tested before the embedding service
    exists, and so the model behind it can change without touching this module.
    """

    def embed_text(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class SearchFilters:
    """Hard constraints. Everything here excludes, none of it ranks."""

    categories: tuple[Category, ...] = ()
    color_families: tuple[ColorFamily, ...] = ()
    brand_ids: tuple[int, ...] = ()
    min_price_usd_cents: int | None = None
    max_price_usd_cents: int | None = None
    # A size the shopper wears, with the system it is stated in. Matching is
    # exact: converting between systems is brand-specific, so a global
    # conversion here would quietly return the wrong sizes.
    sizes: tuple[tuple[SizeSystem, str], ...] = ()
    require_in_stock: bool = False
    exclude_brand_ids: tuple[int, ...] = ()


@dataclass
class SearchResult:
    """One catalog hit, in the compact shape an agent receives."""

    product_id: int
    title: str
    brand: str | None
    category: str | None
    color_family: str | None
    price_usd_cents: int | None
    retailer: str | None
    url: str | None
    image_url: str | None
    in_stock: bool | None
    score: float = 0.0
    matched_by: tuple[str, ...] = ()
    # How many further colourways of this style were collapsed behind this
    # result, so the agent can say "also in four other colours" rather than
    # letting the shopper discover it by clicking through.
    other_colourways: int = 0


@dataclass
class SearchDiagnostics:
    """What each ranker contributed. Surfaced so a bad result set can be
    explained rather than guessed at."""

    vector_candidates: int = 0
    lexical_candidates: int = 0
    fused: int = 0
    queries: int = 0
    notes: list[str] = field(default_factory=list)


def _base_query() -> Select[Any]:
    """Products joined to their cheapest live offer.

    An offer join rather than a subquery on price: the shopper is buying a
    specific offer at a specific retailer, so the row that survives filtering has
    to be the row they can actually click.
    """
    return (
        select(
            Product.__table__.c.id.label("product_id"),
            Product.__table__.c.title,
            Product.__table__.c.category,
            Product.__table__.c.color_family,
            Product.__table__.c.description,
            Brand.__table__.c.name.label("brand"),
            Offer.__table__.c.id.label("offer_id"),
            Offer.__table__.c.price_usd_cents,
            Offer.__table__.c.url,
            Offer.__table__.c.in_stock,
            Retailer.__table__.c.name.label("retailer"),
        )
        .select_from(Product.__table__)
        .join(Offer.__table__, Offer.__table__.c.product_id == Product.__table__.c.id)
        .join(Retailer.__table__, Retailer.__table__.c.id == Offer.__table__.c.retailer_id)
        .outerjoin(Brand.__table__, Brand.__table__.c.id == Product.__table__.c.brand_id)
    )


def _apply_filters(statement: Select[Any], filters: SearchFilters) -> Select[Any]:
    conditions: list[Any] = []
    if filters.categories:
        conditions.append(Product.__table__.c.category.in_(filters.categories))
    if filters.color_families:
        conditions.append(Product.__table__.c.color_family.in_(filters.color_families))
    if filters.brand_ids:
        conditions.append(Product.__table__.c.brand_id.in_(filters.brand_ids))
    if filters.exclude_brand_ids:
        # A brand the shopper avoids must not surface even when it matches
        # perfectly, so this excludes rather than down-ranks. Products with no
        # brand are kept: unknown is not the excluded brand.
        conditions.append(
            or_(
                Product.__table__.c.brand_id.is_(None),
                Product.__table__.c.brand_id.notin_(filters.exclude_brand_ids),
            )
        )
    if filters.min_price_usd_cents is not None:
        conditions.append(Offer.__table__.c.price_usd_cents >= filters.min_price_usd_cents)
    if filters.max_price_usd_cents is not None:
        conditions.append(Offer.__table__.c.price_usd_cents <= filters.max_price_usd_cents)
    if filters.require_in_stock:
        # Only a known true passes. Null is unknown, and showing an unknown as
        # available is how a shopper reaches a sold-out page.
        conditions.append(Offer.__table__.c.in_stock.is_(True))
    if filters.sizes:
        size_conditions = [
            and_(
                OfferSize.__table__.c.size_system == system,
                OfferSize.__table__.c.size_value == value,
            )
            for system, value in filters.sizes
        ]
        available = (
            select(OfferSize.__table__.c.offer_id)
            .where(or_(*size_conditions))
            .where(
                or_(
                    OfferSize.__table__.c.in_stock.is_(True),
                    OfferSize.__table__.c.in_stock.is_(None),
                )
            )
        )
        conditions.append(Offer.__table__.c.id.in_(available))
    if conditions:
        statement = statement.where(and_(*conditions))
    return statement


def _lexical_rank(
    connection: Connection, query: str, filters: SearchFilters, diagnostics: SearchDiagnostics
) -> list[int]:
    """Rank by Postgres full-text relevance over title and description."""
    if not query.strip():
        return []
    # This expression is mirrored by the ix_products_search_document index. It
    # concatenates with || rather than concat_ws because concat_ws is only
    # STABLE and cannot appear in an index expression; the two must stay
    # character-for-character identical or Postgres plans a sequential scan.
    document = func.to_tsvector(
        "english",
        Product.__table__.c.title + " " + func.coalesce(Product.__table__.c.description, ""),
    )
    search = func.plainto_tsquery("english", query)
    statement = _apply_filters(_base_query(), filters).where(document.op("@@")(search))
    statement = statement.order_by(func.ts_rank(document, search).desc()).limit(CANDIDATE_DEPTH)
    diagnostics.queries += 1
    rows = connection.execute(statement).mappings().all()
    diagnostics.lexical_candidates = len(rows)
    return [row["product_id"] for row in rows]


def _vector_rank(
    connection: Connection,
    embedding: list[float] | None,
    filters: SearchFilters,
    diagnostics: SearchDiagnostics,
) -> list[int]:
    """Rank by cosine distance in the catalog's embedding space.

    Products without an embedding are skipped rather than treated as distant:
    embeddings backfill asynchronously, and a product that has not been embedded
    yet is unranked by this ranker, not badly ranked by it.
    """
    if embedding is None:
        diagnostics.notes.append("vector ranker skipped: no query embedding")
        return []
    statement = _apply_filters(_base_query(), filters).where(
        Product.__table__.c.embedding.isnot(None)
    )
    statement = statement.order_by(Product.__table__.c.embedding.cosine_distance(embedding)).limit(
        CANDIDATE_DEPTH
    )
    diagnostics.queries += 1
    rows = connection.execute(statement).mappings().all()
    diagnostics.vector_candidates = len(rows)
    if not rows:
        diagnostics.notes.append("vector ranker returned nothing: catalog not embedded yet")
    return [row["product_id"] for row in rows]


def _fuse(rankings: dict[str, list[int]]) -> dict[int, tuple[float, tuple[str, ...]]]:
    """Reciprocal Rank Fusion over the rankers that produced anything."""
    scores: dict[int, float] = {}
    sources: dict[int, list[str]] = {}
    for name, ranking in rankings.items():
        for position, product_id in enumerate(ranking):
            scores[product_id] = scores.get(product_id, 0.0) + 1.0 / (RRF_K + position + 1)
            sources.setdefault(product_id, []).append(name)
    return {pid: (score, tuple(sources[pid])) for pid, score in scores.items()}


def search_catalog(
    connection: Connection,
    *,
    query: str = "",
    filters: SearchFilters | None = None,
    embedder: Embedder | None = None,
    limit: int = 8,
) -> tuple[list[SearchResult], SearchDiagnostics]:
    """Find purchasable items matching a query under hard constraints.

    Returns few results on purpose. The agent reasons over what comes back, and
    passing it fifty products costs tokens on forty-two it will not use.
    """
    filters = filters or SearchFilters()
    diagnostics = SearchDiagnostics()

    embedding = embedder.embed_text(query) if embedder and query.strip() else None
    rankings = {
        "vector": _vector_rank(connection, embedding, filters, diagnostics),
        "lexical": _lexical_rank(connection, query, filters, diagnostics),
    }
    fused = _fuse({name: ids for name, ids in rankings.items() if ids})

    if not fused:
        # No query, or nothing matched either ranker. Filters alone still define
        # a valid result set - "show me black dresses under $200" needs no query.
        statement = (
            _apply_filters(_base_query(), filters)
            .order_by(Offer.__table__.c.price_usd_cents.asc().nullslast())
            .limit(limit)
        )
        diagnostics.queries += 1
        rows = connection.execute(statement).mappings().all()
        diagnostics.notes.append("fell back to filters only")
        return _hydrate(connection, rows, {}, diagnostics, limit), diagnostics

    ordered = sorted(fused.items(), key=lambda item: item[1][0], reverse=True)[:limit]
    diagnostics.fused = len(fused)
    wanted = [product_id for product_id, _ in ordered]

    statement = _apply_filters(_base_query(), filters).where(Product.__table__.c.id.in_(wanted))
    diagnostics.queries += 1
    rows = connection.execute(statement).mappings().all()
    return _hydrate(connection, rows, dict(ordered), diagnostics, limit), diagnostics


def _hydrate(
    connection: Connection,
    rows: Sequence[Any],
    scored: dict[int, tuple[float, tuple[str, ...]]],
    diagnostics: SearchDiagnostics,
    limit: int,
) -> list[SearchResult]:
    """Build compact results, keeping the cheapest offer per product.

    One image query for the whole page rather than one per product: the same
    one-query-per-relationship rule the GraphQL loader follows.
    """
    cheapest: dict[int, Any] = {}
    for row in rows:
        current = cheapest.get(row["product_id"])
        if current is None:
            cheapest[row["product_id"]] = row
            continue
        incumbent = current["price_usd_cents"]
        challenger = row["price_usd_cents"]
        if incumbent is None or (challenger is not None and challenger < incumbent):
            cheapest[row["product_id"]] = row

    images: dict[int, str] = {}
    if cheapest:
        diagnostics.queries += 1
        image_rows = (
            connection.execute(
                select(
                    ProductImage.__table__.c.product_id,
                    ProductImage.__table__.c.source_url,
                    ProductImage.__table__.c.position,
                )
                .where(ProductImage.__table__.c.product_id.in_(list(cheapest)))
                .order_by(ProductImage.__table__.c.position)
            )
            .mappings()
            .all()
        )
        for image in image_rows:
            images.setdefault(image["product_id"], image["source_url"])

    results = [
        SearchResult(
            product_id=row["product_id"],
            title=row["title"],
            brand=row["brand"],
            category=row["category"].value if row["category"] else None,
            color_family=row["color_family"].value if row["color_family"] else None,
            price_usd_cents=row["price_usd_cents"],
            retailer=row["retailer"],
            url=row["url"],
            image_url=images.get(row["product_id"]),
            in_stock=row["in_stock"],
            score=scored.get(row["product_id"], (0.0, ()))[0],
            matched_by=scored.get(row["product_id"], (0.0, ()))[1],
        )
        for row in cheapest.values()
    ]
    results.sort(key=lambda result: (-result.score, result.price_usd_cents or 1 << 31))
    return _collapse_colourways(results, limit)


def _style_key(result: SearchResult) -> tuple[str, str]:
    """What makes two results the same garment in different colours.

    Colourway splitting gives each colour its own product with its own id, so
    identity has to come from the brand and the style name rather than the row.
    The colour is stripped from the title first, since merchandisers append it
    ("Barrel Jean | Washed Black") and leaving it in makes every colourway look
    like a different style, which is exactly the collapse this is trying to do.
    """
    stem = _TITLE_SEPARATOR.split(result.title)[0].strip().lower()
    return ((result.brand or "").lower(), stem)


def _collapse_colourways(results: list[SearchResult], limit: int) -> list[SearchResult]:
    """Keep the best few colourways per style, and count the rest.

    Order is preserved, so the highest-ranked colourway of a style is the one
    kept. Nothing is discarded silently: the survivors carry a count of what was
    folded behind them.
    """
    kept: list[SearchResult] = []
    seen: dict[tuple[str, str], int] = {}
    folded: dict[tuple[str, str], int] = {}

    for result in results:
        key = _style_key(result)
        count = seen.get(key, 0)
        if count < MAX_PER_STYLE and len(kept) < limit:
            seen[key] = count + 1
            kept.append(result)
        else:
            folded[key] = folded.get(key, 0) + 1

    for result in kept:
        result.other_colourways = folded.get(_style_key(result), 0)
    return kept
