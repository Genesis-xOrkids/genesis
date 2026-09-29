---
title: Catalog Supply (C1–C4)
type: project
sources: [ROADMAP.md, scripts/catalog_coverage.py, intelligence/catalog/search.py, intelligence/catalog/sizes.py, intelligence/catalog/vocabulary.py]
related: ["[[current-state]]", "[[source-agnostic-core]]", "[[hybrid-catalog-search]]", "[[embeddings-and-vectors]]", "[[catalog-sources]]", "[[fashion-taxonomy]]", "[[no-silent-fallbacks]]", "[[null-means-unknown]]", "[[styling-intelligence]]"]
created: 2026-09-07
last-updated: 2026-09-29
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

1,932 of those offers (2026-09-24) had a product with no category at all, so
they could be placed neither inside nor outside the excluded categories. That
figure is stale once PR #66's re-ingest runs: the vocabulary work below resolves
most of them, and it removes home goods from both of C2's denominators. The script
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
sized — so new storefronts arrive carrying a share of the same gap.

**The cause was measured on 2026-09-27, and it was mostly labels, not one-size
items.** A sample of every registered storefront's `products.json` (36,968 offers
in sized categories, 77.3% sized, against 75.7% on the hosted catalog) was run
through the connector label by label. The largest unread shapes were letter sizes
written with a measurement (Taylor Stitch `XS - 36`, ~1,500 offers), spelled out
(Marine Layer `Extra Small`, ~1,080), Tentree's `ONE` (446), and a `Length`
option read as the size (Girlfriend's leggings). The single-variant `Default
Title` shape accounted for ~310 offers, and it stays unknown: it says the listing
has no options, not that the garment is one size, and one of the sampled ones is
a sock 3-pack filed under a product type ending `/M` ([[null-means-unknown]]).
Reading the unambiguous shapes moves the sample to 86.4%, an estimated ~86% on the
hosted catalog, after a re-ingest that also retires size rows the source no longer
states (PR #64). What remains is mostly sizes in systems the enum does not have —
girls' sizes written `XS (4/5)` or `4T` (~1,200 offers), bra band and cup (~205),
sizes for men and women at once (~180) — plus home goods and colour-only bags
that belong to the non-apparel and category work. Those systems are an open
question below.

**Category coverage moved on vocabulary and a boundary rule, not on breadth.**
On 2026-09-27 the hosted catalog carried a resolved category on 88.8% of 41,926
products. The uncategorised ones were concentrated in a few storefronts, and
they were words the vocabulary lacked, not garments it could not know. Organic
Basics, Knix, Negative and Pepper sell underwear, and the vocabulary had no
lingerie terms at all. Rothy's names its shoes "The Driver" and "Mary Jane".
Cozy Earth, Hill House Home and Alo sell towels, bedding, gift cards and loyalty
rewards through the same feed as their clothing. PR #66 did two things (see
[[fashion-taxonomy]]):

- It completed `intelligence/catalog/vocabulary.py` against the existing
  `Category` enum.
- It made connectors turn away records that are not apparel, a rule the user
  decided on 2026-09-27. Ingestion removes what earlier
  runs let in, in the same run.

Measured on a 4-page sample of all 27 storefronts, 14.6% of 24,391 products were
uncategorised before and 2.0% of 23,368 after, with 339 records turned away. The
same sample ingested end to end into a local database read 85.4% before and 98.0%
after. The hosted estimate is ~98.5% once a person re-ingests after merge.
Removing non-apparel shrinks both C2 denominators: the product count, and the
offers the size measure is taken over. Home goods carry no size, so the size
share rose too, from 81.9% to 86.7% on that sample.

"Resolved" is not "correct". About 150 of the sample's newly resolved products
were decided by a tag or a description rather than the title or the product type.
After the hosted re-ingest, the coordinator runs `evals/retrieval` and
spot-checks those.

The workflow exists: `probe_storefronts.py` vets candidates without
adding them, `seed_storefronts.py --file storefronts.txt` registers those that
pass, `ingest_catalog.py` runs, and `catalog_coverage.py` says where that left
the four measures. `storefront-scout` ([[agent-network]]) owns
the first half of it: it probes candidates and opens a pull request adding the
ones that pass, and a person runs the seed and the ingest after that merges.
Twelve of twenty candidates probed ingestible on the first pass, so roughly ten
more registered storefronts should clear the product, brand and category targets;
the size target does not move with them, and after the label work it waits on
the size systems the enum lacks.

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

**Its two search defects are closed.** Splitting records per colourway left
3,557 titles mapping to more than one product, with one shoe existing as 49
products. Search folds those to at most two colourways per style, and since PR
#63 it refills the page after folding rather than returning it short. The same
PR stopped the filters-only fallback from ordering by price. It now puts known
in stock first, then lets brands take turns, then shows newest to the catalog
first. Both are recorded on [[hybrid-catalog-search]]. Category precision has not
been re-measured on the hosted catalog since that change.

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

## Open questions

- **Size systems the enum does not have.** Girls' sizes (`XS (4/5)`, `4T`, `10Y`,
  ~1,200 unsized offers in the 2026-09-27 sample), bra band and cup (`34B`, ~205)
  and sizes stated for men and women at once (`W10/M9`, ~180) each need a
  `SizeSystem` value and a migration. Together they are about as large as what is
  left between C2's size measure and its 90% target (PR #64).
- **Hair accessories and Rothy's model names.** Both are left without a category
  on purpose. Hair accessories have no `Category` value (96 products in the
  2026-09-28 sample). Rothy's titles such as "The Point II" name a model, not a
  garment (244 products). Both are listed as open decisions.
