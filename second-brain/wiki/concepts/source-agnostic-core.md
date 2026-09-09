---
title: Source-agnostic core domain
type: concept
sources: [CLAUDE.md, PLAN.md]
related: ["[[one-write-door]]", "[[provider-agnostic-intelligence]]", "[[catalog-sources]]", "[[no-silent-fallbacks]]", "[[fashion-taxonomy]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

Every external source is translated at the boundary into four canonical shapes —
`Product`, `Offer`, `TrendObservation`, `BrandDoc` — and **the core domain never
references a source's field names, identifiers, or enums** (CLAUDE.md, Service
design).

The sources being translated: Shopify, Klarna, Rakuten, CJ, Awin, Impact,
Instagram Graph, Pinterest, Tagwalk, and PLM exports. See [[catalog-sources]].

Adapters own auth, retries, rate limits and translation. Nothing outside an
adapter knows the external shape.

## The rule that gives it teeth

A merchandiser's facet is not a fact. CLAUDE.md, Data:

> Before modeling a field off a source's facet, dropdown, or vendor label, find
> what the source actually contains. A retailer's "Fit: Relaxed" or "Occasion:
> Cocktail" facet is a merchandiser's interpretation; the photos, measurements, and
> copy hold the atomic facts. A trend vendor's "trend score" is an interpretation
> of observations.

A vendor value may be kept when it is genuinely queried, but only *alongside* the
atomic values it was derived from, never instead of them. And when the underlying
data has not been seen: go get it, or ask, before the vendor's values become the
schema.

This is why sizing is `size_system` plus `size_value` plus measured dimensions
rather than the string "M (US 8)", and why a colour is `color_hex` plus
`color_family` rather than a retailer's swatch name.

## Where the boundary lives in the repo

`intelligence/catalog/`: `connectors/` (`shopify.py`, `shopify_public.py`,
`affiliate_feed.py`, `base.py`) for the source shapes, then `normalized.py`,
`money.py`, `fx.py`, `color.py`, `sizes.py`, `vocabulary.py`, `ucp.py` for the
translation, then `ingest.py` writing through [[one-write-door]].

The unit conventions the normalizers target come from CLAUDE.md, Naming: time
fields end `_at`; no `is_` prefix on booleans; unit suffixes `_cm`, `_grams`,
`_usd_cents`, `_pct`.

## The failure mode it is guarding against

A shared normalizer that runs without error can still be silently wrong at a new
field's bounds (CLAUDE.md, Design review mindset): a price check assuming USD
accepts JPY 12,000 as $12,000; a size normalizer assuming numerics silently drops
"XS". The test is whether the number is *plausible*, not whether the code ran.

## Status

Built for three connector types. ROADMAP.md App. A: "Currency, colour and size
normalization; three connectors; quarantine for malformed records". Breadth, not
mechanism, is the open gap — see [[catalog-supply]].
