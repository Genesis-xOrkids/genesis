---
title: Atomic facts, not derivations
type: concept
sources: [CLAUDE.md, PLAN.md]
related: ["[[provenance-creates-rows]]", "[[null-means-unknown]]", "[[database-is-the-api]]", "[[source-agnostic-core]]", "[[fashion-taxonomy]]", "[[trend-corpus]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

Two rules that look similar and do different work (CLAUDE.md, Data).

**Store atomic facts, not shorthand.** Composite labels get decomposed. "Black
high-rise skinny jeans" is `category=jeans`, `rise=high`, `fit=skinny`,
`color_hex`, `color_family=black`. "M (US 8)" is `size_system` and `size_value`,
plus measured dimensions where the size chart gives them.

**Store facts, not derivations.** The backend may fill a canonical atomic value
the source omitted — `price_usd_cents` from price, currency and a *recorded* rate;
`color_family` from hex; `category` via the taxonomy mapping — and the output is
still an atomic fact. Interpretations are not: `is_on_sale`, `is_trending`, "fits
her palette", and latest-by-`recorded_at` are computed where they are used, never
stored on a domain row.

## The test for which side a value is on

Ask whether the value can become wrong without the underlying data changing. A
normalized price cannot: it is a function of price, currency and a rate that were
all recorded. `is_on_sale` can — the moment the comparison price moves, the stored
boolean is a lie that nothing will correct. Anything in the second category is a
second source of truth that drifts.

A trend label is the clean case: "quiet luxury, +12%" is derived, so what gets
stored is the attribute observations it came from. See [[trend-corpus]].

## No JSON, anywhere

Structured, typed columns. First-class garment attributes are columns; the long
tail lives in typed attribute rows,
`product_attributes(product_id, attribute, value_id, confidence, source)`; raw
source payloads live in S3, not the database (CLAUDE.md, Data). PLAN.md §3.4
states it again against its own model sketch: braces and brackets in the sketch
are shorthand for typed child tables, "never JSON columns".

## The related naming rule

**Names identify; variants specialize.** A `Product` is (brand, style, colourway)
when the colourway changes what the item is. Size — and anything else that only
changes which unit ships — lives on `Variant`/`Offer`, never in the product name.

This rule has a live consequence. Splitting source records one-per-colourway fixed
colour coverage but made 3,557 titles map to more than one product, with one shoe
existing as 49 products, so a search returning eight results can return the same
style eight times. Correctly modelled, wrong at the point of use — the fix belongs
in retrieval, not in the schema. See [[hybrid-catalog-search]].

## The check before adding a column

Grep for the fact elsewhere in the schema first (CLAUDE.md, Design review
mindset). A duplicated fact with no enforcement that the copies agree is a bug
waiting for its first disagreement, and a wider new field is often worse than an
existing narrower one that already expresses the distinction. The result of that
check goes in the PR description or migration docstring — which existing thing was
checked and why this is not a duplicate — rather than being left for a reviewer to
re-derive.
