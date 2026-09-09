---
title: Commerce and Compliance (X1–X4)
type: project
sources: [ROADMAP.md, PLAN.md]
related: ["[[catalog-sources]]", "[[image-provenance]]", "[[tenant-isolation]]", "[[tool-results-are-data]]", "[[consumer-application]]", "[[risk-register]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The track that runs alongside the critical path rather than on it, because its
first item is **calendar time, not engineering time** (ROADMAP.md §5.4).

## X1 — Partner applications ⬜ *(start now)*

Affiliate network publisher accounts for department-store and large-retailer
coverage, plus a **published agent profile document**, which the sanctioned
commerce protocol requires merchants to fetch before they will answer catalog
calls.

Acceptance: at least one network approved, agent profile reachable, and a catalog
call succeeding against a real merchant.

**Blocked by approval queues, not by us.** This is the item the roadmap says to
file immediately, independent of engineering progress — and risk R2 says why it
may not land: affiliate applications get rejected for lack of traffic, a classic
chicken-and-egg. Mitigation is to lead with platform-native and aggregator routes
that do not gate on volume. See [[catalog-sources]] and [[risk-register]].

## X2 — Attribution and monetization ⬜

Affiliate link decoration and click attribution, plus subscription billing
scaffolding **dormant until there is something to charge for**. Acceptance: a
click attributable end to end in a test transaction. Depends on X1 and A3.

## X3 — Disclosure and policy ⬜

Three obligations, all designed in rather than retrofitted:

- **FTC material-connection disclosure before the first click.** Consumer Review
  Rule penalties run to ~$53K per violation, and rankings must not be secretly
  influenced by commission rates — if they are, that must be disclosed too
  (PLAN.md §5).
- **AI-generated content labelling and provenance**, per EU AI Act Art. 50,
  **adopted globally rather than gated by geography**. See [[image-provenance]].
- **Privacy policy, consent flows, and a working data-subject deletion path.**

Acceptance: disclosure components covered by snapshot tests, deletion verified
across every store, counsel review before public launch.

Depends on A3 and A4. **On the critical path to public launch, not after it** —
which is the mitigation for risk R6.

## X4 — Security readiness ⬜

Threat model recorded. Tenant isolation tests ([[tenant-isolation]]) and injection
tests against untrusted catalog text ([[tool-results-are-data]]) in CI. Penetration
test scheduled before enterprise general availability.

Depends on A5.

## The compliance constraints that already shape the schema

Not milestones, but design constraints already in force (PLAN.md §7):

- **No biometric templates.** Colour analysis derives a palette and discards the
  image; no face geometry, no body scans. BIPA carries a private right of action.
- **Age gate 16+** at MVP.
- **Consent ledger** with DSAR and erase workflows that also purge AgentCore
  Memory, vectors and caches — not just database rows.
- **EU data residency** via Bedrock EU geo profiles or `inference_geo` when serving
  EU tenants.
