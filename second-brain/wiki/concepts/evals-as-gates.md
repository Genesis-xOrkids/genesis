---
title: Evals gate prompts the way tests gate code
type: concept
sources: [CLAUDE.md, PLAN.md, ROADMAP.md]
related: ["[[pre-ship-checklist]]", "[[styling-intelligence]]", "[[hybrid-catalog-search]]", "[[model-tiering]]", "[[provenance-creates-rows]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

"Evals gate prompt and model changes the way tests gate code. **A prompt edit
without an eval run is not done**" (CLAUDE.md, Agents). The eval run is on the
[[pre-ship-checklist]], and it blocks deploys on regression (PLAN.md §12).

## Built before the thing it measures

[[styling-intelligence]] S1 — the evaluation harness — precedes S2 (intake) and S3
(the stylist agent itself) on the roadmap. The stated reason (ROADMAP.md §5.2):

> what cannot be measured cannot be tuned, and a rubric written after the fact
> tends to describe whatever the model already does.

Its acceptance criteria are about the harness, not the agent: a baseline recorded
for a deliberately naive stylist, judge agreement with human scoring checked on a
sample, and **a seeded regression caught by the gate**. The last one is the test
that the gate works at all.

## The stylist rubric

Seven dimensions (ROADMAP.md §5.2, PLAN.md §4.8): profile adherence, budget
adherence, occasion fit, brand fit, **item availability as a hard failure**,
assortment diversity, and rationale quality. Graded by Opus 5 as judge over 200
synthetic and 100 real intake→outfit cases, spot-checked by hand. Target: ≥ 4.0/5.0
mean, set at baseline and then held as a regression gate.

Availability being a hard failure rather than a scored dimension follows from the
objective: "a recommendation you cannot buy is not a recommendation" (ROADMAP.md §3).

## The other four suites

- **Catalog QA**: dead-link rate, price staleness, attribute precision on a
  labelled 1K set.
- **Trend pipeline QA**: extraction precision and recall against a stylist-labelled
  set, plus back-testing trend scores against subsequent assortment shifts.
- **B2B design QA**: brand-fit scores against stylist ratings; IP-risk
  false-negative audits.
- **Online**: thumbs, save and purchase rates, session length, A/B on effort levels.

## The failure this discipline actually caught

C3's original acceptance metric — recall@8 on a labelled set — would have passed
before the work started, because the labelled queries were generated from product
titles and lexical matching already scored 95% (ROADMAP.md §5.1, correction dated
2026-09-06). It was replaced by category precision on semantic queries, which
moved 20% → 79%.

**The generalisable rule: a metric that passes before the work begins is measuring
something else.** Check that before trusting a green gate. See
[[hybrid-catalog-search]].

## Evals as the condition for cost decisions

Downgrading a model is gated on evals showing parity, never on price alone
(CLAUDE.md, Agents; PLAN.md §4.7 lever 9). This is the mechanism that keeps
[[unit-economics]] from silently becoming a quality decision — see
[[model-tiering]].

## Status

Harness for retrieval exists (`evals/retrieval/`, with `dataset.py` and `run.py`)
and produced the C3 numbers. The stylist rubric harness is S1 and not built.
