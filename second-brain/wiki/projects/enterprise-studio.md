---
title: Enterprise Studio (E1–E6) — deferred
type: project
sources: [ROADMAP.md, PLAN.md]
related: ["[[trend-corpus]]", "[[tenant-isolation]]", "[[image-provenance]]", "[[image-generation]]", "[[open-decisions]]", "[[risk-register]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

Half the business, and deliberately not started (ROADMAP.md §5.5).

**The reasoning**: the consumer track proves the shared core, the catalog and the
styling engine, all of which the enterprise product reuses. Building both at once
with the current team would slow both.

**The trigger to start**, written down precisely so the decision is deliberate
rather than drifting: a signed design partner, or the consumer demo reaching its
§3 targets — whichever comes first.

## The outline, kept so the shape is not lost

| Milestone | Scope |
|---|---|
| E1 | Tenant onboarding, single sign-on, per-tenant isolation and keys |
| E2 | Brand knowledge ingestion from lookbooks and line sheets into brand codes with evidence |
| E3 | Trend corpus and attribute time series, from licensed runway data, platform APIs, and owned assortment analytics |
| E4 | Trend reports with citations, numbers computed in the database rather than by a model |
| E5 | Concept generation, iteration tooling, and an intellectual-property critic |
| E6 | Authorship records and exports to product lifecycle management systems |

## The cost gate

The trend corpus carries a data-licensing line item that has not been committed to
— the single largest discretionary cost in [[unit-economics]]. **That decision
gates E3 and should be made before E1 starts, not during** (ROADMAP.md §5.5). It
is open decision D5, whose default if unanswered is that the enterprise track does
not start.

## What the studio does, from PLAN.md §2.2

Brand DNA ingestion from lookbooks, campaign imagery, line sheets, PLM exports and
tone documents into a versioned **Brand Knowledge Base** — signature silhouettes,
palettes, materials, details, do/don't rules. A stylist workspace whose ratings and
"more like this / never this" annotations become a per-tenant reinforcement signal.
Attribute-level trend intelligence ([[trend-corpus]]). Concept generation from a
brief plus brand DNA plus selected trends. Iteration by recolor, replace, inpaint
([[image-generation]]). Export to PDF, PPTX and PLM CSV with C2PA manifests
([[image-provenance]]).

Five agents back it (PLAN.md §4.3): brand ingestion, trend analyst, design, a
**critic/IP agent** on Opus 5 at `xhigh` effort running trade-dress similarity and
text-in-image checks, and export.

## The market position

PLAN.md §2.3: trend tools (Heuritech, WGSN, EDITED, Trendalytics, Launchmetrics,
Tagwalk) don't generate; design tools (Raspberry AI, Mercer, The New Black,
Refabric, NewArc) don't quantify trends or learn a brand's DNA from its stylists'
feedback. The combination with an auditable IP trail is the differentiator, and
the trend vendors are expected to be **partners or data vendors rather than
head-on competitors** in year one.

## The risk of it never starting

R8 in ROADMAP.md §7: "Enterprise track never starts because consumer work expands"
— medium impact, **high likelihood**. The mitigation is the written trigger above.
Naming a high-likelihood risk whose only mitigation is a sentence in a document is
itself worth noticing.

## Status

Not built beyond a tenant table.
