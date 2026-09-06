"""Add storefronts to the ingestion registry.

Takes domains that :mod:`scripts.probe_storefronts` reported as ingestible and
writes them through the same write door everything else uses, so re-running is
an update rather than a duplicate.

    PYTHONPATH=. uv run python scripts/seed_storefronts.py --file storefronts.txt
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from sqlalchemy import select

from api.genesis_api.db import write_session
from api.genesis_api.models import Storefront
from api.genesis_api.models.enums import StorefrontRoute
from api.genesis_api.writer import WriteSpec, write
from intelligence.catalog.connectors.shopify_public import fetch_storefront_profile
from intelligence.catalog.fetching import PoliteFetcher


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domains", nargs="*")
    parser.add_argument("--file", help="file with one domain per line")
    args = parser.parse_args()

    domains = list(args.domains)
    if args.file:
        domains += [
            line.split("#")[0].strip()
            for line in pathlib.Path(args.file).read_text().splitlines()
            if line.split("#")[0].strip()
        ]
    if not domains:
        parser.error("give at least one domain, or --file")

    with PoliteFetcher() as fetcher, write_session() as session:
        specs = []
        for domain in domains:
            # Read the storefront's own metadata rather than asking the operator
            # to type a currency: the store states it, and a typo here would
            # misprice an entire retailer.
            profile = fetch_storefront_profile(fetcher, domain)
            specs.append(
                WriteSpec(
                    entity="Storefront",
                    natural_key={"domain": domain},
                    values={
                        "retailer_name": profile.retailer_name,
                        "brand_name": profile.brand_name,
                        "currency": profile.currency,
                        "size_system": profile.size_system,
                        "route": StorefrontRoute.unknown,
                        "enabled": True,
                    },
                )
            )
            print(f"  {domain:30s} {profile.retailer_name} ({profile.currency})")
        results = write(session, specs)

    created = sum(1 for r in results if r.created)
    print(f"\n{created} added, {len(results) - created} updated")

    with write_session() as session:
        total = len(list(session.scalars(select(Storefront))))
    print(f"{total} storefronts in the registry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
