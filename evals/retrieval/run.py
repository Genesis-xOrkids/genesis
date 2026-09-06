"""Measure retrieval quality, with and without embeddings.

The point of running both arms is attribution. "Recall improved" says nothing if
the only number you have is the current one; the question is whether the
embedding work paid for itself, and that needs the lexical-only baseline
measured on the same queries in the same run.

    PYTHONPATH=. uv run python evals/retrieval/run.py
    PYTHONPATH=. uv run python evals/retrieval/run.py --count 50   # quick pass
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field

from sqlalchemy.engine import Connection

from api.genesis_api.db import engine
from evals.retrieval.dataset import (
    SEMANTIC_QUERIES,
    KnownItemQuery,
    SemanticQuery,
    known_item_queries,
)
from intelligence.catalog.search import search_catalog
from services.embeddings import FashionEmbedder

TOP_K = 8
_SEPARATOR = re.compile(r"\s+[|–—-]\s+|\|")


@dataclass
class ArmResult:
    name: str
    known_item_hits: int = 0
    known_item_total: int = 0
    category_hits: int = 0
    category_scored: int = 0
    color_hits: int = 0
    color_scored: int = 0
    empty_results: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def recall_at_k(self) -> float:
        return self.known_item_hits / self.known_item_total if self.known_item_total else 0.0

    @property
    def category_precision(self) -> float:
        return self.category_hits / self.category_scored if self.category_scored else 0.0

    @property
    def color_precision(self) -> float:
        return self.color_hits / self.color_scored if self.color_scored else 0.0


def _style(title: str) -> str:
    return _SEPARATOR.split(title)[0].strip().lower()


def score_known_item(
    connection: Connection, queries: list[KnownItemQuery], embedder: FashionEmbedder | None
) -> ArmResult:
    """Did the intended style come back in the top results?

    Matched on style rather than product id, because colourway splitting means
    the same garment exists under many ids and returning a different colour of
    the right garment is a hit, not a miss.
    """
    arm = ArmResult(name="with embeddings" if embedder else "lexical only")
    for item in queries:
        results, _ = search_catalog(connection, query=item.query, embedder=embedder, limit=TOP_K)
        arm.known_item_total += 1
        if not results:
            arm.empty_results += 1
            continue
        if any(_style(result.title) == item.style for result in results):
            arm.known_item_hits += 1
    return arm


def score_semantic(
    connection: Connection,
    queries: list[SemanticQuery],
    embedder: FashionEmbedder | None,
    arm: ArmResult,
) -> None:
    """Do the results satisfy the constraint the query implies?

    Scored per returned item rather than per query. "Black slip dress" has
    hundreds of right answers, so what matters is the share of the eight results
    that are actually black slip dresses.
    """
    for item in queries:
        results, _ = search_catalog(connection, query=item.query, embedder=embedder, limit=TOP_K)
        if not results:
            arm.empty_results += 1
            continue
        if item.category is not None:
            arm.category_scored += len(results)
            arm.category_hits += sum(1 for r in results if r.category == item.category.value)
        if item.color is not None:
            arm.color_scored += len(results)
            arm.color_hits += sum(1 for r in results if r.color_family == item.color.value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--recall-target", type=float, default=0.80)
    args = parser.parse_args()

    embedder = FashionEmbedder()
    arms: list[ArmResult] = []

    with engine().connect() as connection:
        items = known_item_queries(connection, count=args.count)
        print(f"  {len(items)} known-item queries, {len(SEMANTIC_QUERIES)} semantic queries\n")

        for active in (None, embedder):
            arm = score_known_item(connection, items, active)
            score_semantic(connection, SEMANTIC_QUERIES, active, arm)
            arms.append(arm)

    header = f"{'arm':18s} {'recall@8':>9s} {'category':>9s} {'colour':>8s} {'empty':>6s}"
    print(header)
    print("-" * len(header))
    for arm in arms:
        print(
            f"{arm.name:18s} {arm.recall_at_k:9.1%} {arm.category_precision:9.1%} "
            f"{arm.color_precision:8.1%} {arm.empty_results:6d}"
        )

    baseline, treatment = arms
    delta = treatment.recall_at_k - baseline.recall_at_k
    print(f"\n  recall delta from embeddings: {delta:+.1%}")
    print(
        f"  category precision delta:     "
        f"{treatment.category_precision - baseline.category_precision:+.1%}"
    )

    if treatment.recall_at_k < args.recall_target:
        print(f"\n  BELOW TARGET: recall@8 {treatment.recall_at_k:.1%} < {args.recall_target:.0%}")
        return 1
    print(f"\n  recall@8 {treatment.recall_at_k:.1%} meets the {args.recall_target:.0%} target")
    return 0


if __name__ == "__main__":
    sys.exit(main())
