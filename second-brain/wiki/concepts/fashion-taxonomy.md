---
title: The fashion taxonomy
type: concept
sources: [PLAN.md, CLAUDE.md]
related: ["[[atomic-facts-not-derivations]]", "[[source-agnostic-core]]", "[[trend-corpus]]", "[[hybrid-catalog-search]]", "[[catalog-supply]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The shared vocabulary both halves of the product write into. Based on
**Fashionpedia** — 27 apparel categories, 19 parts, 294 attributes — extended with
two additions (PLAN.md §4.6):

- **An explicit silhouette vocabulary**: A-line, column, sheath, balloon, cocoon,
  drop-waist, boxy, oversized, slim, cropped, elongated, plus shoulder lines, rise,
  hem, and volume placement.
- **Style descriptors** — quiet luxury, gorpcore, office-siren, boho revival —
  **versioned per season**.

## Closed sets are enums; open sets are tables

The distinction is a schema rule (CLAUDE.md, Code):

- **Postgres enums for closed value sets.** Lowercase values, member names equal
  values: `drop_shoulder = "drop_shoulder"`, never `"drop-shoulder"`. SQLAlchemy
  uses member names as DB labels.
- **Reference tables for open or seasonally versioned vocabularies** — aesthetics,
  trend labels, brand codes — with a surrogate integer `id` and a unique natural
  key.

Silhouette is a closed set and belongs in an enum. "Quiet luxury" is not: it is
seasonal, it is contested, and it will be joined by three more next year. Putting
it in an enum would make every new aesthetic a migration.

Reference tables get an integer `id` even when they have a natural key, because
every GraphQL-traversed table needs one ([[database-is-the-api]]).

## Why the long tail is rows, not columns

First-class garment attributes are columns; everything else is
`product_attributes(product_id, attribute, value_id, confidence, source)`. 294
Fashionpedia attributes cannot each be a column, and they cannot be JSON either
(CLAUDE.md forbids JSON/JSONB outright). Typed attribute rows are the third
option, and they carry confidence and provenance for free — which is what lets a
model extraction and a retailer value sit in the same place
([[provenance-creates-rows]]).

## Where it is filled from

Attribute extraction runs Haiku 4.5 in batch over product, wardrobe and trend
images, at 50% off (PLAN.md §4.6, §9). Images are downscaled to ≤1,092 px on the
long edge and cropped to the garment before the vision call — roughly 1,600 tokens
per image (PLAN.md §4.7 lever 4).

## The gap it cannot close by itself

Silhouette coverage sits near 18% and is deliberately **not** treated as a
[[catalog-supply]] C2 breadth gap: silhouette is rarely stated in product text, so
more storefronts will not move it. It needs the vision work in C3. Measured
2026-09-05.
