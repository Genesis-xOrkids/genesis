---
title: Styling Intelligence (S1–S4)
type: project
sources: [ROADMAP.md, PLAN.md]
related: ["[[evals-as-gates]]", "[[hybrid-catalog-search]]", "[[provenance-creates-rows]]", "[[agent-runtime]]", "[[model-tiering]]", "[[catalog-supply]]", "[[consumer-application]]", "[[unit-economics]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The product's actual value (ROADMAP.md §5.2). Nothing in it is built.

## S1 — Evaluation harness ⬜

Built **before** the agent, deliberately. A rubric over seven dimensions, a
dataset of personas crossed with occasions, model-graded with a strong judge and
spot-checked by hand, running in CI on any prompt, tool-schema or model change and
blocking on regression. See [[evals-as-gates]] for the rubric and the reasoning.

Depends on C1, for a catalog to recommend from.

## S2 — Intake and style profile ⬜

Conversational intake producing a structured profile, written through
[[one-write-door]] into the profile tables. Two rules carry it:

- **Extraction is a fact with provenance and confidence, never an assertion**
  ([[provenance-creates-rows]]).
- **Users can see and correct everything inferred about them.**

Acceptance: test transcripts produce valid profiles with no schema violations,
every stored preference traces to something the user said, and correction
round-trips.

Depends on S1.

## S3 — Stylist agent and outfit composition ⬜ *(critical path)*

The agent, with tools for profile, catalog search, availability and weather.

**Outfit composition is constraint satisfaction over slots, not free-form
generation**, so budget and size constraints are structurally enforced rather than
requested politely. A rationale per outfit cites the profile facts it drew on.
Alternates at three price points per slot.

PLAN.md §4.3 gives the tool list: `get_profile`, `get_wardrobe`,
`search_catalog(query, filters, k)`, `verify_availability`, `price_history`,
`weather`, `size_guidance`, `render_lookbook`, `try_on` — on Opus 5, with product
text treated as untrusted ([[tool-results-are-data]]).

Acceptance: rubric ≥ 4.0, **every surfaced item purchasable at render**, p95
first-token < 2.5s, cost per session inside [[unit-economics]].

Depends on S1, S2 and C3 — the only milestone depending on all three tracks.

## S4 — Memory across sessions ⬜

Preferences learned from behaviour, stored with provenance alongside stated ones;
user-visible, user-editable, user-deletable.

Acceptance: a second session demonstrably reflects the first session's feedback,
and **deletion removes the memory everywhere, including any derived index**. The
clause about derived indexes is the hard part — a deleted preference that survives
in a vector index is not deleted.

Memory has an injection rule of its own: a memory must trace to a user utterance,
not a tool result ([[tool-results-are-data]]).

Depends on S3.

## The agent cast this track eventually needs

From PLAN.md §4.3, beyond the stylist itself: an **intake** agent (Opus 5, medium
effort), a **shopping** agent gated on human-in-the-loop checkout with per-session
spending caps, and an async **memory curator** on Haiku 4.5. A thin supervisor
delegates to specialists while keeping its system prompt and tool list stable, so
delegation does not cost a cache namespace ([[prompt-caching]]).
