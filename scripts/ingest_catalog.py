"""Run catalog ingestion across the storefront registry.

    PYTHONPATH=. uv run python scripts/ingest_catalog.py
    PYTHONPATH=. uv run python scripts/ingest_catalog.py --domain www.everlane.com
    PYTHONPATH=. uv run python scripts/ingest_catalog.py --max-pages 2   # smoke run

Safe to re-run. Every write goes through the upsert writer keyed on natural
keys, so a second pass updates rather than duplicating.
"""

from __future__ import annotations

import argparse
import sys

from api.genesis_api.models.enums import IngestionRunStatus
from intelligence.catalog.fx import current_rates
from intelligence.pipelines.ingest_storefronts import run

# Above this share of unreadable records, a source has probably changed shape
# rather than simply carrying a few odd listings.
QUARANTINE_ALERT_RATE = 0.05


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", action="append", dest="domains")
    parser.add_argument("--page-size", type=int, default=250)
    parser.add_argument("--max-pages", type=int, default=40)
    args = parser.parse_args()

    # No session here on purpose: the runner commits per storefront, so one
    # slow or failing source cannot roll back another's work.
    summary = run(
        current_rates(),
        domains=args.domains,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )

    header = f"{'storefront':28s} {'status':11s} {'route':12s} {'seen':>6s} {'prod':>6s} {'offers':>6s} {'quar':>5s}"
    print(header)
    print("-" * len(header))
    for outcome in summary.outcomes:
        report = outcome.report
        print(
            f"{outcome.domain:28s} {outcome.status.value:11s} {outcome.route.value:12s} "
            f"{outcome.records_seen:6d} "
            f"{report.products_written if report else 0:6d} "
            f"{report.offers_written if report else 0:6d} "
            f"{report.quarantined if report else 0:5d}"
            + (f"  {outcome.error[:52]}" if outcome.error else "")
        )

    print(
        f"\n{summary.records_seen} records seen, "
        f"{summary.products_written} products, {summary.offers_written} offers, "
        f"{summary.quarantined} quarantined ({summary.quarantine_rate:.1%})"
    )

    failed = summary.by_status(IngestionRunStatus.failed)
    blocked = summary.by_status(IngestionRunStatus.blocked)
    disallowed = summary.by_status(IngestionRunStatus.disallowed)
    if blocked or disallowed:
        print(f"{len(blocked)} blocked, {len(disallowed)} disallowed by robots")

    # A failed run and a high quarantine rate are different problems and exit
    # differently, so a scheduler can treat them differently.
    if failed:
        print(f"FAILED: {len(failed)} storefront(s)")
        return 1
    if summary.quarantine_rate > QUARANTINE_ALERT_RATE:
        print(
            f"quarantine rate above {QUARANTINE_ALERT_RATE:.0%} - a source may have changed shape"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
