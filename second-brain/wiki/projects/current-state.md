---
title: Current state and success targets
type: project
sources: [ROADMAP.md, README.md]
related: ["[[roadmap]]", "[[catalog-supply]]", "[[styling-intelligence]]", "[[consumer-application]]", "[[risk-register]]", "[[pre-ship-checklist]]", "[[database-choice]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

What exists, measured against the repository on 2026-09-05 rather than recalled
(ROADMAP.md §2), and the eight numbers that define done.

## Measured, 2026-09-05

| Dimension | Value |
|---|---|
| Automated tests | 384 |
| Database tables | 21 |
| Applied migrations | 3 |
| Catalog connectors | 3 |
| Products in the catalog | 0 |
| Deployed user-facing surfaces | 0 |

The last two rows are the whole roadmap. ROADMAP.md §1: the binding constraint has
shifted from infrastructure to two gaps — **the catalog is empty, and there is
nothing to look at.**

The product count has since moved: 21,055 products across 34 brands as of
2026-09-05, after [[catalog-supply]] C1 and a partial C2.

## Built

Data model and generated GraphQL API ([[database-is-the-api]]); single write door
with idempotent upserts ([[one-write-door]]); model gateway across three platforms
with per-call cost attribution ([[provider-agnostic-intelligence]]); catalog
normalization for currency, colour and sizing plus three connectors
([[source-agnostic-core]]); sanctioned-protocol discovery; hybrid search with hard
constraint filters ([[hybrid-catalog-search]]); CI enforcing eight gates; hosted
Postgres with pgvector ([[database-choice]]).

## Not built

Any user interface. The stylist agent itself. Authentication, hosting, billing,
affiliate attribution. And the entire enterprise studio beyond a tenant table.

Embeddings appear on the not-built list in ROADMAP.md §2 but have since shipped —
commits `ff2b5fa` and `367058a`. The document has not been updated to reflect it.

## The eight targets

Each with the roadmap's own reason for the number (ROADMAP.md §3):

| Measure | Target | Why this number |
|---|---|---|
| Catalog size | ≥ 25,000 products, ≥ 50 brands | Below this, outfit composition runs out of options in common categories |
| Dead-link rate | < 2% of surfaced items | Above it the product feels broken |
| Items purchasable at render | 100% | A recommendation you cannot buy is not a recommendation |
| Stylist rubric score | ≥ 4.0 / 5.0 mean | Set at baseline, then held as a regression gate |
| Retrieval category precision | ≥ 0.75 on semantic queries | The agent only sees eight results |
| Retrieval recall@8 | ≥ 0.90 on known-item queries | A regression guard, not a quality measure |
| First-token latency | p95 < 2.5s | Conversational threshold |
| Cost per active user | ≤ $2.40 / month | From [[unit-economics]] |

## The six non-goals

Written down so they do not accumulate as unspoken scope (ROADMAP.md §4): mobile
applications, agentic checkout, design generation, migration to AWS, fine-tuning
any model, and a human stylist marketplace.

Two carry reasons worth keeping: agentic checkout is out because merchants require
contemporaneous human approval before payment and the sanctioned protocol is
explicit about it; fine-tuning is out because retrieval quality and prompting have
not been exhausted, and tuning before they are is premature.

## Sequencing

```
  C1 ──► C2 ──► C3 ──────────► C4
  S1 ──────────► S2 ──► S3 ──► S4
  A1 ──► A2 ─────────────► A3 ──► A4 ──► A5
  X1 ═══(external queue)══════► X2 ──► X3 ──► X4
```

**Critical path: `C1 → C2 → C3 → S3 → A3 → A5`.** Everything else has slack.
[[consumer-application]] A1 and [[styling-intelligence]] S1 depend on nothing and
can start on day one; [[commerce-and-compliance]] X1 is pure calendar time and
should be filed immediately.

The temptation the roadmap names explicitly: starting the application before the
catalog is real "produces a convincing demo of an empty product, which teaches you
nothing and is expensive to unwind" (ROADMAP.md §6).

Written for one engineer with an AI pair. Two engineers would compress the
calendar by roughly a third; the plan does not assume that.
