---
title: Getting real items — the layered catalog
type: decision
sources: [PLAN.md, ROADMAP.md]
related: ["[[source-agnostic-core]]", "[[catalog-supply]]", "[[commerce-and-compliance]]", "[[trend-corpus]]", "[[risk-register]]"]
created: 2026-09-07
last-updated: 2026-09-29
---

## The decision

Layer sanctioned sources rather than pick one, and **do not scrape at launch**
(PLAN.md §1 decision 5, §5). The three criteria being traded off are coverage,
monetization, and legality.

| Source | Coverage | Monetization |
|---|---|---|
| **Shopify Catalog API + Agentic Storefronts** | Millions of Shopify merchants — most DTC and Instagram-native brands; default-on since Mar 2026 | Promoted placements; UCP checkout |
| **Klarna Agentic Product Protocol** | 100M+ products, 400M prices, 12–13 markets | Klarna checkout / affiliate |
| **UCP** (Google/Shopify-led; Target, Walmart, Wayfair, Etsy, Zalando) | catalog + cart since Mar 2026 | agentic checkout, later |
| **Rakuten, CJ, Awin, Impact** | Department stores, luxury e-tailers, premium DTC | Affiliate commissions |
| Affiliate.com aggregator | 30+ networks, ~1B products normalized | Pass-through `[verify]` |
| Amazon Creators API | Amazon catalog | **Deferred** — needs 10 qualifying sales / 30 days |

Shopify is the best single source for the Instagram-native brands the consumer
product is anchored on. Amazon is deferred on a pure chicken-and-egg: it requires
traffic that does not exist yet.

## Why not scrape

Not a squeamishness argument — a foundation argument. Scraping logged-out public
pages survived *Meta v. Bright Data* (2024), but contract terms and EU
text-and-data-mining opt-out rules "make it a poor foundation for an enterprise
product" (PLAN.md §4.6). If it ever happens: logged-out public pages only,
robots.txt and TDM opt-outs honoured, legal review first, never behind a login or
ToS. The same reasoning governs [[trend-corpus]].

## The ingestion path

Feeds and APIs → S3 raw → normalize (schema, currency, sizes, gender, category
mapping) → dedupe by GTIN/MPN then by FashionSigLIP image-embedding near-duplicate
check → Haiku 4.5 batch attribute extraction → embeddings → Postgres
`Product`/`Offer` → nightly availability re-check for anything shown in the last
30 days → price history.

**Show only offers verified within 24 hours; re-verify the primary pick at render
time.** That is [[catalog-supply]] C4, and it is what makes "100% purchasable at
render" achievable rather than aspirational.

Everything after the first arrow is [[source-agnostic-core]]: the core domain
never sees a source's field names.

## The commercial dependency

Access to the affiliate layer is an approval queue, not an engineering task —
[[commerce-and-compliance]] X1, and risk R2. The mitigation is to lead with
platform-native routes (Shopify, Klarna) that do not gate on traffic volume, which
is also why C1 was built against public storefronts first.

## Only apparel enters the catalog

**Decided by the user on 2026-09-27.** Records that are not fashion items are
rejected at the connector boundary and quarantined with a named reason. That
covers home textiles, bath goods, gift cards and services, loyalty rewards,
personal care and fitness equipment. It is not a vendor filter bolted on
downstream, and it does not apply to one source only.

The rule is conservative by instruction:

- **Only unambiguous evidence rejects.** The title must name a non-apparel item.
- **Anything worn protects.** A title that names a garment keeps the record,
  and bundles of garments are apparel. A "Bath Robe" and a "Bra Trio Bundle"
  stay; a "Bath Towel Set" goes. The merchant's category protects a title that
  names nothing itself, but not one that names a non-apparel item: a "Luxe Bath
  Towel" on a "Towels & Robes" shelf is still a towel.
- **Unclear titles stay.** A title that names neither a garment nor a
  non-apparel item is kept, uncategorised.
- **Bath and towel wraps are worn garments** (decided 2026-09-29, applying the
  rule above). They are kept, as sleepwear.

The ingest run that first rejects a record removes the rows the feed wrote for it
before the rule existed. That removal takes only products whose provenance is
the feed's. It skips any product carrying an offer from another writer, or a
long-tail attribute a person or a model labelled, since those rows would cascade
away with it. The size retirement that runs beside it (PR #64) is narrower still:
it deletes only size rows of offers the same run has just written, and size
rows record no provenance of their own. PR #66 implements the rule in
`vocabulary.not_apparel`, and [[catalog-supply]] records the measured effect on
C2.

## What was learned by doing it

Sanctioned-protocol adoption "looked universal on sampled storefronts, which is
encouraging but was a small sample" (ROADMAP.md §7 R1). Twelve of twenty probed
candidates were ingestible on the first pass. `intelligence/catalog/ucp.py`
implements the discovery path; commit `71cb409` — "Add UCP discovery, so
storefronts are read through the path they sanction".
