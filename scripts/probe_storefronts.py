"""Check whether candidate storefronts can be ingested, before adding them.

Adding a storefront to the registry that turns out to be unreadable costs a
failed run every night until someone notices. This answers the question first:
does it serve a public product feed, does it advertise the sanctioned protocol,
what currency does it state, and does a sample actually normalize.

    PYTHONPATH=. uv run python scripts/probe_storefronts.py domain [domain ...]
    PYTHONPATH=. uv run python scripts/probe_storefronts.py --file candidates.txt
"""

from __future__ import annotations

import argparse
import datetime
import itertools
import pathlib
import sys
from dataclasses import dataclass

from intelligence.catalog.connectors.shopify_public import (
    ShopifyPublicConnector,
    fetch_storefront_profile,
    iter_storefront_products,
)
from intelligence.catalog.fetching import Blocked, DisallowedByRobots, FetchError, PoliteFetcher
from intelligence.catalog.money import FxRates
from intelligence.catalog.ucp import UcpUnavailable, discover


@dataclass
class Probe:
    domain: str
    verdict: str
    ucp: bool = False
    currency: str | None = None
    retailer: str | None = None
    sampled: int = 0
    normalized: int = 0
    quarantined: int = 0
    note: str = ""


def probe(fetcher: PoliteFetcher, domain: str, *, sample: int = 12) -> Probe:
    rates = FxRates(as_of=datetime.datetime.now(datetime.UTC), usd_per_unit={})

    ucp = False
    try:
        ucp = discover(fetcher, domain).offers_catalog
    except (UcpUnavailable, FetchError):
        ucp = False

    try:
        profile = fetch_storefront_profile(fetcher, domain)
    except DisallowedByRobots as exc:
        return Probe(domain, "disallowed", ucp=ucp, note=str(exc)[:60])
    except Blocked:
        return Probe(domain, "blocked", ucp=ucp, note="bot management (403)")
    except (FetchError, ValueError) as exc:
        return Probe(domain, "no-metadata", ucp=ucp, note=f"{type(exc).__name__}: {str(exc)[:50]}")

    try:
        records = list(
            itertools.islice(iter_storefront_products(fetcher, profile, page_size=sample), sample)
        )
    except Blocked:
        return Probe(domain, "blocked", ucp=ucp, currency=profile.currency, note="feed 403")
    except (FetchError, ValueError) as exc:
        return Probe(
            domain,
            "no-feed",
            ucp=ucp,
            currency=profile.currency,
            note=f"{type(exc).__name__}: {str(exc)[:50]}",
        )

    if not records:
        return Probe(
            domain, "empty", ucp=ucp, currency=profile.currency, retailer=profile.retailer_name
        )

    result = ShopifyPublicConnector(profile=profile, rates=rates).normalize(records)
    return Probe(
        domain=domain,
        verdict="ok" if result.products else "unusable",
        ucp=ucp,
        currency=profile.currency,
        retailer=profile.retailer_name,
        sampled=len(records),
        normalized=len(result.products),
        quarantined=len(result.failures),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domains", nargs="*")
    parser.add_argument("--file", help="file with one domain per line")
    parser.add_argument("--sample", type=int, default=12)
    args = parser.parse_args()

    domains = list(args.domains)
    if args.file:
        domains += [
            line.strip()
            for line in pathlib.Path(args.file).read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    if not domains:
        parser.error("give at least one domain, or --file")

    header = f"{'domain':28s} {'verdict':12s} {'ucp':4s} {'cur':4s} {'sample':>6s} {'ok':>4s} {'quar':>5s}  note"
    print(header)
    print("-" * len(header))

    results: list[Probe] = []
    with PoliteFetcher() as fetcher:
        for domain in domains:
            result = probe(fetcher, domain, sample=args.sample)
            results.append(result)
            print(
                f"{result.domain:28s} {result.verdict:12s} "
                f"{'yes' if result.ucp else '-':4s} {result.currency or '-':4s} "
                f"{result.sampled:6d} {result.normalized:4d} {result.quarantined:5d}  {result.note}"
            )

    usable = [r for r in results if r.verdict == "ok"]
    print(f"\n{len(usable)}/{len(results)} ingestible")
    if usable:
        print("\nadd with:")
        for r in usable:
            print(f"  {r.domain}  # {r.retailer} ({r.currency})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
