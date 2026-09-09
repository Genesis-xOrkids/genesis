---
title: Provenance creates rows, never columns
type: concept
sources: [CLAUDE.md]
related: ["[[one-write-door]]", "[[atomic-facts-not-derivations]]", "[[null-means-unknown]]", "[[evals-as-gates]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

A fact's origin is a value in a `source` column, not a separate column or table.
A preference stated at intake, inferred from behaviour, or edited by the user
lands in **the same column** with a provenance row — never in
`preference_intake` and `preference_inferred` (CLAUDE.md, Data).

A new source may mint new rows — a photographed wardrobe item next to an imported
one — but never a parallel column or table for a fact that already has a home.

## Why this is the load-bearing version of "one write path"

Without it, [[one-write-door]] decays quietly. Each new source
arrives with a plausible argument for its own column, every reader then has to
know the precedence order between five columns, and that order lives in reader
code rather than in the data. With provenance as rows, the precedence rule is one
rule — latest write wins — and it lives in the writer.

## The model-output case

This is where the rule earns its keep. **Model extractions are facts with
confidence, not truth** (CLAUDE.md, Agents): store `value` + `confidence` +
provenance `source = model` in the same columns as any other source. Unknown stays
null, never a default ([[null-means-unknown]]).

The consequence is that a Haiku-extracted garment attribute and a retailer-supplied
one are the same shape, comparable, and rankable by confidence — which is what
makes it possible to measure extraction precision against a labelled set at all
([[evals-as-gates]]).

The corresponding product promise: users can see and correct everything inferred
about them, and every stored preference traces to something the user said
(ROADMAP.md §5.2 S2).

## Where the schema carries it

`product_attributes(product_id, attribute, value_id, confidence, source)` and
`WardrobeItemAttribute(wardrobe_item_id, attribute, value_id, confidence, source)`
(PLAN.md §3.4). Both are typed attribute rows, not JSON, and both carry the
provenance and confidence columns on the same row as the value.
