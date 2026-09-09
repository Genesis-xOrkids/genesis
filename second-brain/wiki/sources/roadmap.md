---
title: ROADMAP.md — the delivery plan
type: source-summary
sources: [ROADMAP.md]
related: ["[[plan]]", "[[engineering-constitution]]", "[[current-state]]", "[[catalog-supply]]", "[[styling-intelligence]]", "[[consumer-application]]", "[[commerce-and-compliance]]", "[[enterprise-studio]]", "[[risk-register]]", "[[open-decisions]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The delivery plan: what is next, in what order, and why. Dated 2026-09-05, status
"proposed, awaiting approval", horizon roughly one quarter to consumer demo
readiness. Where [[plan]] answers "what should this be", this answers "what do we
do on Monday".

Its opening move is the one that matters: the shared core [[plan]] specified is
built and verified, so **the binding constraint has shifted from infrastructure to
two gaps — the catalog is empty and there is nothing to look at** (ROADMAP.md §1).

## What it decides

- **Eight measurable success targets** rather than a feeling of done, each with a
  stated reason for the number (ROADMAP.md §3). See [[current-state]].
- **Six named non-goals** — mobile, agentic checkout, design generation, the AWS
  migration, fine-tuning, and a human stylist marketplace — written down so they
  do not accumulate as unspoken scope (§4).
- **Five workstreams**: [[catalog-supply]], [[styling-intelligence]],
  [[consumer-application]], [[commerce-and-compliance]], [[enterprise-studio]].
- **A critical path**: `C1 → C2 → C3 → S3 → A3 → A5` (§6). Everything else has slack.
- **The enterprise half is deferred behind an explicit written trigger** (§5.5):
  a signed design partner, or the consumer demo hitting its §3 targets.
- **A definition of done applying to every milestone** (§9), extending the
  [[pre-ship-checklist]] in [[engineering-constitution]].

## What is unusual about it

Three things worth naming, because they are choices rather than conventions:

- **It measures before it claims.** §2 opens "Verified against the repository on
  2026-09-05, not recalled", and every number in it is a count, not an estimate.
- **It corrects itself in place.** §5.1 C3 carries a dated correction (2026-09-06)
  stating that its original acceptance metric was wrong and would have passed
  before the work started, because recall@8 on title-generated queries is already
  95% under lexical matching. The original metric is left visible next to the
  correction rather than edited away. See [[hybrid-catalog-search]].
- **It builds evaluation before the thing evaluated.** S1 precedes S2 and S3
  deliberately: "a rubric written after the fact tends to describe whatever the
  model already does" (§5.2). See [[evals-as-gates]].

## Section map

| § | Subject | Wiki page |
|---|---|---|
| 2, App. A | Current state, measured | [[current-state]] |
| 3 | Success targets | [[current-state]] |
| 5.1 | Catalog Supply, C1–C4 | [[catalog-supply]] |
| 5.2 | Styling Intelligence, S1–S4 | [[styling-intelligence]] |
| 5.3 | Consumer Application, A1–A5 | [[consumer-application]] |
| 5.4 | Commerce and Compliance, X1–X4 | [[commerce-and-compliance]] |
| 5.5 | Enterprise Studio, E1–E6 | [[enterprise-studio]] |
| 7 | Risk register R1–R8 | [[risk-register]] |
| 8 | Open decisions D1–D6 | [[open-decisions]] |
| 9 | Definition of done | [[pre-ship-checklist]] |

## What it is silent on

Two measured gaps found on 2026-09-05 are not in it, because they were discovered
after it was written: the [[catalog-supply]] C2 shortfall against its own §3
targets, and the colourway duplication in search results. Both are recorded on
their workstream pages.
