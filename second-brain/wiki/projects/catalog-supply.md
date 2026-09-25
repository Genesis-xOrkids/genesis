---
title: Catalog Supply (C1–C4)
type: project
sources: [ROADMAP.md, scripts/catalog_coverage.py]
related: ["[[current-state]]", "[[source-agnostic-core]]", "[[hybrid-catalog-search]]", "[[embeddings-and-vectors]]", "[[catalog-sources]]", "[[fashion-taxonomy]]", "[[no-silent-fallbacks]]", "[[null-means-unknown]]", "[[styling-intelligence]]"]
created: 2026-09-07
last-updated: 2026-09-24
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
| Offers with size data, over every offer | 73% | 90% |

**The four measures are computed now, not asserted.** `scripts/catalog_coverage.py`
prints them in SQL against whichever database it is pointed at, each beside its
target, plus a product count for every category (commits `8021ac9`, `a4b9fa4`).
Run it for current numbers: the table above stays as measured on 2026-09-05 and
nothing refreshes it.

**What "usable size data" means was settled by a person, not by the script.**
`ROADMAP.md` §5.1 carries a dated **Correction, 2026-09-22**: it means size data
*present*, measured over **offers whose category carries sizes** — bag, belt,
jewelry, eyewear, watch and scarf excluded, because a size the garment does not
have is not a gap this milestone can close. Offers rather than products is now
the roadmap's own wording, which settles the disagreement this page used to
record. Availability is deliberately not part of it: stock turns over hourly, and
a breadth milestone gated on it could never close, so the share a shopper could
buy is C4's signal and is reported beside the target rather than scored against
it.

Both readings, measured 2026-09-24 against the hosted catalog by
`catalog_coverage.py`:

| Reading | Share | Denominator |
|---|---|---|
| Size data present — **the C2 criterion**, 14.8 points short of its 90% target | 75.2% | 20,033 offers outside the unsized categories |
| Carrying a size in stock or of unknown stock — **C4's signal, not a criterion** | 55.3% | the same 20,033 offers |
| Size data present over every offer — the pre-correction reading, superseded | 73.3% | 21,055 offers |

1,932 of those offers (2026-09-24) have a product with no category at all, so
they can be placed neither inside nor outside the excluded categories. The script
keeps them in the denominator, because null is unknown rather than known-unsized
([[null-means-unknown]]), and prints what the measure would read without them
(75.6%) so the choice is auditable. 1,022 offers are in the excluded categories
and 358 of those carry a size row anyway — a belt has a size — which the
exclusion drops with the rest: it is a statement about the category, not about
the row.

**Three of the four gaps are breadth; the size gap is not.** Products, brands and
category coverage move together by adding storefronts. Size data does not: on
2026-09-24 the 4,966 offers in sized categories with no size row were spread
across eleven of the twelve storefronts ingested — only Outdoor Voices is fully
sized — so new storefronts arrive carrying a share of the same gap. It is
heaviest where one-size items are common (hosiery 32% of its offers sized, hat
49%, shirt 47%), which is the shape the connector's own skips would leave: it
writes no size row for a single-variant `Default Title` product, nor for a label
`parse_size` cannot read ([[no-silent-fallbacks]]). Nobody has confirmed that
against the source payloads yet, so the cause is a reading, not a measurement.
The workflow exists: `probe_storefronts.py` vets candidates without
adding them, `seed_storefronts.py --file storefronts.txt` registers those that
pass, `ingest_catalog.py` runs, and `catalog_coverage.py` says where that left
the four measures. `storefront-scout` ([[agent-network]]) owns
the first half of it: it probes candidates and opens a pull request adding the
ones that pass, and a person runs the seed and the ingest after that merges.
Twelve of twenty candidates probed ingestible on the first pass, so roughly ten
more registered storefronts should clear the product, brand and category targets;
the size target needs connector work beside them.

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

Its size of the problem is already measured, because C2's report prints it beside
the target it is not part of: on 2026-09-24, 3,995 offers in sized categories were
sized and sold out in every size, and 1,737 were buyable in exactly one size,
against 55.3% carrying a size a size-filtered search would match. Those are the
numbers to watch when this starts.
