---
title: The trend corpus
type: concept
sources: [PLAN.md, CLAUDE.md, ROADMAP.md]
related: ["[[enterprise-studio]]", "[[fashion-taxonomy]]", "[[atomic-facts-not-derivations]]", "[[tool-results-are-data]]", "[[unit-economics]]", "[[catalog-sources]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The evidence base for the enterprise half, built entirely from legitimately
available data. PLAN.md §4.6 opens with the reality check that shapes it:

- Instagram's Graph API allows hashtag search only for Business/Creator accounts,
  30 unique hashtags per rolling 7 days, top media only. **No public firehose.**
- TikTok's Research API is restricted to non-commercial academic use.
- Pinterest's Trends API is enterprise-partner gated, ≤50 results, current day,
  and its terms forbid caching most data.
- Google Trends API is an application-gated alpha.
- Scraping logged-out pages survived *Meta v. Bright Data* (2024), but contract
  terms and EU text-and-data-mining opt-outs make it a poor foundation for an
  enterprise product.

## The six legitimate layers

1. **Runway and show data, licensed** — Tagwalk, Launchmetrics.
2. **Trend intelligence partners, budget-dependent** — Heuritech, EDITED,
   Trendalytics, WGSN. Ingested as attributed signals, never resold.
3. **Platform trend APIs as available** — Pinterest Trends, Google Trends alpha,
   and Instagram Graph for **brand customers' own accounts**, connected by the
   customer through OAuth.
4. **Market assortment analytics, owned** — the same catalog feeds that power the
   consumer side, tracked daily: new-arrival attribute mix, price architecture,
   markdown timing, stock-out proxies by silhouette. EDITED-style analytics from
   data already being ingested.
5. **Owned consumer signals, proprietary** — consented B2C engagement, aggregated
   and k-anonymized, never per-user.
6. **Editorial and brand-published content** via web fetch, with citations.

**The moat is stated explicitly**: fusing assortment, runway and owned signals —
not scraping. Layers 4 and 5 are the ones a competitor cannot buy, and both are
byproducts of the consumer product. This is the concrete form of "the two halves
feed each other".

## Observations are facts; series are computations

The schema follows [[atomic-facts-not-derivations]] exactly. `TrendObservation`
rows carry attributes and a segment tag (runway / designer / contemporary /
Instagram-native / mass / social). A trend label — "quiet luxury, +12%" — is
derived and is never stored on a domain row.

`TrendSeries` rows are the computation: per attribute × segment × week, share,
velocity (Δ share), acceleration, and cross-segment lead/lag (runway →
contemporary → mass). CLAUDE.md, ML: these aggregates are **explicit, dated,
versioned rows that record their method and sample size. They are facts about a
computation, never cached interpretations on domain rows, and they are recomputed,
not patched.**

## The ML shape

CLAUDE.md, ML and trend analytics: raw dimensions rather than engineered features,
one column per real-world thing; categorical dimensions as parallel columns so a
look with three attributes is three active columns rather than one "style"
integer; **sequence over snapshot**, feeding chronological event streams so models
learn trend acceleration and taste drift without hand-built features; and all
events carry signal, not just purchases — dwell, dismissals, returns, stylist
annotations, edits to generated concepts.

## Honesty as a product requirement

Heuritech's claimed ~90% accuracy comes from years of labelled data. PLAN.md §4.6:
"be honest in the UI: show confidence and sample size, and offer human analyst
review as a premium tier." Paired with the [[tool-results-are-data]] rule that
numbers come from SQL and the model only narrates, with citations to the
underlying observations.

## The cost gate

The trend corpus carries a data-licensing line item that has not been committed to
— the largest discretionary cost in the model. ROADMAP.md §5.5 makes it a gate:
that decision blocks E3 and **should be made before E1 starts, not during**. It is
open decision D5. See [[open-decisions]].

## Status

Not built. Deferred with [[enterprise-studio]].
