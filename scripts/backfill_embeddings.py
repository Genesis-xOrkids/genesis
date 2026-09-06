"""Embed catalog products so search can match on meaning.

    PYTHONPATH=. uv run python scripts/backfill_embeddings.py
    PYTHONPATH=. uv run python scripts/backfill_embeddings.py --limit 256   # smoke run

Incremental and re-runnable: only products with no embedding are considered, so
a run that dies partway resumes rather than starting over.
"""

from __future__ import annotations

import argparse
import sys
import time

from api.genesis_api.db import write_session
from intelligence.pipelines.backfill_embeddings import backfill, outstanding
from services.embeddings import FashionEmbedder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100_000)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--device", help="override torch device (mps, cuda, cpu)")
    args = parser.parse_args()

    embedder = FashionEmbedder(device=args.device)
    started = time.perf_counter()

    with write_session() as session:
        before = outstanding(session)
        print(f"  {before:,} products without an embedding")
        report = backfill(session, embedder, batch_size=args.batch_size, limit=args.limit)
        after = outstanding(session)

    elapsed = time.perf_counter() - started
    rate = report.embedded / elapsed if elapsed else 0
    print(
        f"\n  embedded {report.embedded:,} of {report.considered:,} considered "
        f"in {elapsed:.0f}s ({rate:.0f}/s)"
    )
    print(f"    from image: {report.embedded_from_image:,}")
    print(f"    from text:  {report.embedded_from_text:,} (image fetch failed)")
    print(f"  {after:,} still without an embedding")
    return 0


if __name__ == "__main__":
    sys.exit(main())
