"""Build a labelled retrieval set from the catalog itself.

Two kinds of query, because they measure different things and only one can be
generated automatically.

**Known-item queries** are derived from a product's own title with the brand and
colourway stripped. The right answer is known: that product, or another colourway
of the same style. This measures whether search can find a specific garment
somebody half-remembers, which is what lexical matching is already decent at and
therefore the honest baseline to beat.

**Semantic queries** are written by hand and scored on whether the results
satisfy a constraint rather than on hitting one row. "Black slip dress" has
hundreds of correct answers, so recall against a single target would be
meaningless; what matters is whether the eight things returned are actually
black slip dresses. This is the capability embeddings are supposed to add, and
the one lexical search fails outright.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from api.genesis_api.models import Brand, Product
from api.genesis_api.models.enums import Category, ColorFamily

_SEPARATOR = re.compile(r"\s+[|–—-]\s+|\|")
_NOISE = re.compile(r"[^a-z0-9\s]")
# Words that identify a merchant rather than a garment. Leaving them in turns a
# retrieval test into a brand-name lookup, which every ranker passes.
_STOPWORDS = {"the", "a", "an", "womens", "mens", "women", "men", "unisex"}


@dataclass(frozen=True)
class KnownItemQuery:
    """A query with one known-correct style."""

    query: str
    product_id: int
    style: str
    brand: str | None


@dataclass(frozen=True)
class SemanticQuery:
    """A query scored on whether results satisfy a constraint."""

    query: str
    category: Category | None = None
    color: ColorFamily | None = None


def _style_stem(title: str) -> str:
    return _SEPARATOR.split(title)[0].strip()


def known_item_queries(
    connection: Connection, *, count: int = 200, seed: int = 20260905
) -> list[KnownItemQuery]:
    """Sample distinct styles and turn each title into a query.

    Sampled across styles rather than products, so a style existing in forty
    colourways does not get forty chances to be found.
    """
    products = Product.__table__
    brands = Brand.__table__
    statement = (
        select(
            func.min(products.c.id).label("product_id"),
            products.c.title,
            brands.c.name.label("brand"),
        )
        .select_from(products)
        .outerjoin(brands, brands.c.id == products.c.brand_id)
        .where(products.c.title.isnot(None))
        .group_by(products.c.title, brands.c.name)
    )
    rows = list(connection.execute(statement).mappings())

    rng = random.Random(seed)
    rng.shuffle(rows)

    queries: list[KnownItemQuery] = []
    for row in rows:
        stem = _style_stem(row["title"])
        words = [
            word
            for word in _NOISE.sub(" ", stem.lower()).split()
            if word and word not in _STOPWORDS
        ]
        # Two words is not a query, it is a guess; skip rather than pad the set.
        if len(words) < 3:
            continue
        queries.append(
            KnownItemQuery(
                query=" ".join(words),
                product_id=row["product_id"],
                style=stem.lower(),
                brand=row["brand"],
            )
        )
        if len(queries) >= count:
            break
    return queries


# Written by hand. These are the shapes a stylist is actually asked for, and
# none of them name a product.
SEMANTIC_QUERIES: list[SemanticQuery] = [
    SemanticQuery("black slip dress for an evening out", Category.dress, ColorFamily.black),
    SemanticQuery("navy wool coat for winter", Category.coat, ColorFamily.navy),
    SemanticQuery("white cotton button down shirt", Category.shirt, ColorFamily.white),
    SemanticQuery("high waisted wide leg denim", Category.jeans, None),
    SemanticQuery("cream cashmere knit for layering", Category.sweater, None),
    SemanticQuery("olive utility trousers", Category.pants, ColorFamily.green),
    SemanticQuery("little black dress", Category.dress, ColorFamily.black),
    SemanticQuery("striped long sleeve top", Category.top, None),
    SemanticQuery("leather ankle boots", Category.boots, None),
    SemanticQuery("oversized blazer for the office", Category.blazer, None),
    SemanticQuery("pleated midi skirt", Category.skirt, None),
    SemanticQuery("chunky wool cardigan", Category.cardigan, None),
    SemanticQuery("white leather sneakers", Category.sneakers, ColorFamily.white),
    SemanticQuery("silk camisole", Category.top, None),
    SemanticQuery("quilted puffer jacket", Category.coat, None),
    SemanticQuery("beige trench coat", Category.coat, ColorFamily.beige),
    SemanticQuery("ribbed tank top", Category.top, None),
    SemanticQuery("linen summer dress", Category.dress, None),
    SemanticQuery("grey marl sweatpants", Category.pants, ColorFamily.gray),
    SemanticQuery("structured leather tote bag", Category.bag, None),
]
