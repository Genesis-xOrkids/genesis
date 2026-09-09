---
title: Hybrid catalog search
type: concept
sources: [PLAN.md, ROADMAP.md, CLAUDE.md]
related: ["[[embeddings-and-vectors]]", "[[catalog-supply]]", "[[fashion-taxonomy]]", "[[atomic-facts-not-derivations]]", "[[evals-as-gates]]", "[[styling-intelligence]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The single retrieval path both agents call. pgvector cosine similarity over
FashionSigLIP text and image embeddings, plus SQL filters (category, price band,
brand, size availability, colour family), plus BM25 on titles, fused by rank, then
reranked, then the top-k handed to the agent as compact JSON — id, brand, title,
price, attributes, image URL (PLAN.md §4.4).

**Never return raw retailer HTML to the model.** That is a retrieval rule and an
injection control at once ([[tool-results-are-data]]).

## Filters are hard constraints, not preferences

Outfit composition is constraint satisfaction over slots rather than free-form
generation, "so budget and size constraints are structurally enforced rather than
requested politely" (ROADMAP.md §5.2 S3). Search carries the same property one
level down: a size or price filter is a `WHERE`, not a hint in a prompt.

## Why it is small on purpose

The agent sees eight results. That number sets the quality bar — "if half are the
wrong garment type it cannot build an outfit" (ROADMAP.md §3) — and it is also the
cost lever: rerank to top-8 and pass compact JSON, never full product pages
(PLAN.md §4.7 lever 5). See [[unit-economics]].

## The metric correction worth remembering

ROADMAP.md §5.1 C3 carries a dated self-correction (2026-09-06). The milestone
originally called for recall@8 on a labelled set. That metric was wrong and would
have passed *before the work started*, because the queries were generated from
product titles and lexical matching already scored 95%.

The replacement: **category precision on semantic queries**, target ≥ 0.75, which
moved from 20% to 79%. Recall@8 is still reported at ≥ 0.90 but explicitly as a
regression guard, not as a measure of semantic quality.

Both the original metric and the correction are recorded here because the roadmap
records both. The general lesson is on [[evals-as-gates]]: a metric that passes
before the work begins is measuring something else.

## Two live defects in the retrieval path

Measured 2026-09-05 by running live searches, and not recorded in ROADMAP.md at
the time of discovery:

- **Colourway duplication.** Splitting source records one-per-colourway fixed
  colour coverage (0% → 80%) but made 3,557 titles map to more than one product;
  one shoe, "The Point", exists as 49 products. Eight results can be the same
  style eight times, which is useless for assembling an outfit. The fix belongs
  *with* C3 rather than after it: both are search work, and shipping semantic
  retrieval on top of a 49-way duplicate problem only makes the duplicates rank
  better.
- **The filters-only fallback sorts by price ascending**, so seven genuinely free
  items — a replacement button, a pouch — surface first on exactly the broad
  queries a new user starts with.

## Status

Built and improved. ROADMAP.md App. A: "Hybrid vector and lexical with rank
fusion; filters enforced as hard constraints". `intelligence/catalog/search.py`,
`evals/retrieval/`. Commits `ff2b5fa` (embed the catalog, collapse colourways in
results) and `367058a` (fix category accuracy: the labels were wrong, not the
retrieval) are the C3 work.
