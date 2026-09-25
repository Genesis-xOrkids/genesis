---
title: Catalog Supply (C1–C4)
type: project
sources: [ROADMAP.md, scripts/catalog_coverage.py]
related: ["[[current-state]]", "[[source-agnostic-core]]", "[[hybrid-catalog-search]]", "[[embeddings-and-vectors]]", "[[catalog-sources]]", "[[fashion-taxonomy]]", "[[no-silent-fallbacks]]", "[[styling-intelligence]]"]
created: 2026-09-07
last-updated: 2026-09-19
---

## What it is

Make the catalog real. First in the sequence because everything downstream is
meaningless without merchandise, and because it is the only major track with no
external blocker (ROADMAP.md §5.1).

## C1 — Storefront registry and ingestion runner ✅

A registry of storefronts (domain, retailer name, route, size-system override), a
job that resolves the route per storefront, pages the source, normalizes, and
writes through [[one-write-door]], plus per-run reporting of products written,
offers written, and quarantined by stage ([[no-silent-fallbacks]]).

Acceptance: ten storefronts ingested end to end, quarantine under 5% with every
reason attributable to a named cause, and **a second run changing no row counts**
— idempotency as an acceptance criterion, not an implementation detail.

Done and merged: commit `5d87a4e`, "Fill the catalog: storefront registry,
ingestion runner, 21k products". Tooling: `scripts/probe_storefronts.py`,
`scripts/seed_storefronts.py`, `scripts/ingest_catalog.py`,
`intelligence/pipelines/ingest_storefronts.py`.

## C2 — Catalog breadth ⚠️ partially complete

Expand the registry to cover the brand mix the target customer actually shops,
across price tiers and categories, with a coverage check so no core category is
under-represented.

**Stalled short of its targets and set aside to start C3.** Measured 2026-09-05:

| Measure | Actual | Target |
|---|---|---|
| Products | 21,055 | 25,000 |
| Brands | 34 | 50 |
| Category coverage | 89.7% | 95% |
| Offers with size data | 73% | 90% |

**The four measures are computed now, not asserted.** `scripts/catalog_coverage.py`
prints them in SQL against whichever database it is pointed at, each beside its
target, plus a product count for every category (commit `8021ac9`). Run it for
current numbers: the table above stays as measured on 2026-09-05 and nothing
refreshes it.

**Two sources disagree about what the size measure is over, and neither is
corrected here.** `ROADMAP.md` §5.1 reads "at least 90% carry usable size data"
with *products* as the subject of the sentence; the table above, and the script,
state it over *offers*, which is what size rows hang off and what a person buys.
The script names both sources where it prints the number.

**Usable is narrower than present.** [[hybrid-catalog-search]] matches a size row
only where `in_stock` is true or unknown, so an offer whose every size has sold
out carries size data the stylist cannot use. The script counts sizes the way
search does, which puts its figure below the 73% above — that one counted any
size row at all.

All four gaps are breadth rather than depth, so they move together by adding
storefronts. The workflow exists: `probe_storefronts.py` vets candidates without
adding them, `seed_storefronts.py --file storefronts.txt` registers those that
pass, `ingest_catalog.py` runs, and `catalog_coverage.py` says where that left
the four measures. `storefront-scout` ([[agent-network]]) owns
the first half of it: it probes candidates and opens a pull request adding the
ones that pass, and a person runs the seed and the ingest after that merges. Twelve of twenty candidates probed ingestible on
the first pass, so roughly ten more registered storefronts should clear every
target.

**Silhouette coverage (~18%) is deliberately not on this list.** Silhouette is
rarely stated in product text, so more storefronts will not move it; it needs the
vision work in C3. See [[fashion-taxonomy]].

## C3 — Embedding service and backfill ✅

Fashion-tuned image and text embeddings behind the existing embedder interface,
which search was already written against, plus a backfill over the catalog,
incremental for new arrivals. Hosted inference first; revisit self-hosting at
volume ([[embeddings-and-vectors]]).

Its acceptance criteria were **corrected in place on 2026-09-06** after the
original metric turned out to pass before the work started. See
[[hybrid-catalog-search]] and [[evals-as-gates]]. Result: category precision on
semantic queries moved 20% → 79%.

Commits `ff2b5fa` (embed the catalog, collapse colourways in results) and
`367058a` (fix category accuracy: the labels were wrong, not the retrieval).

**One defect from this work is still open**: collapsing colourways left 3,557
titles mapping to more than one product, one shoe existing as 49 products, so
eight results can be the same style eight times. Recorded on
[[hybrid-catalog-search]].

## C4 — Freshness ⬜ not started

Re-check price and availability for anything surfaced recently, verify the primary
pick at render time, and retain price history for later sale alerts. Acceptance is
the < 2% dead-link target, measured on a sample of *surfaced* items rather than
the whole catalog — the distinction that keeps the measurement honest and cheap.

Depends on C1 only, so it can run any time.
