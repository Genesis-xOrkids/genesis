# Genesis Delivery Roadmap

| | |
|---|---|
| **Status** | Proposed, awaiting approval |
| **Last updated** | 2026-09-05 |
| **Horizon** | Consumer demo readiness, roughly one quarter |
| **Related** | `PLAN.md` (architecture and research), `CLAUDE.md` (engineering principles) |

---

## 1. Context

`PLAN.md` set out the architecture for both halves of the product. The shared core it describes is built and verified: a schema, an API generated from it, a single write path, model access behind one gateway, a catalog ingestion boundary, and hybrid search. Continuous integration enforces the engineering principles mechanically, and a hosted database is live.

None of that is visible to a customer. There is no interface, no stylist, and no merchandise. The binding constraint has shifted from infrastructure to two concrete gaps: **the catalog is empty**, and **there is nothing to look at**.

This document covers the work from here to a consumer product a stranger can use, plus the deferred enterprise track and the commercial and compliance work that has to land alongside it.

---

## 2. Current state

Verified against the repository on 2026-09-05, not recalled.

| Dimension | Value |
|---|---|
| Automated tests | 384 |
| Database tables | 21 |
| Applied migrations | 3 |
| Catalog connectors | 3 |
| Products in the catalog | 0 |
| Deployed user-facing surfaces | 0 |

**Built.** Data model and generated GraphQL API, single write door with idempotent upserts, model gateway across three platforms with per-call cost attribution, catalog normalization for currency, colour and sizing, connectors for partner APIs, affiliate feeds and public storefronts, sanctioned-protocol discovery, hybrid search with hard-constraint filters, CI enforcing eight gates, hosted Postgres with pgvector.

**Not built.** Any user interface, the stylist agent itself, embeddings, merchandise, authentication, hosting, billing, affiliate attribution, and the entire enterprise studio beyond a tenant table.

---

## 3. Objective

**Primary.** A person who has never seen the product can describe their style and receive outfits assembled from items they can actually buy, in a hosted application, with the recommendation quality measured rather than asserted.

Success is judged on these, all measurable:

| Measure | Target | Why this number |
|---|---|---|
| Catalog size | ≥ 25,000 products across ≥ 50 brands | Below this, outfit composition runs out of options in common categories |
| Dead-link rate | < 2% of surfaced items | The plan's own gate; above it the product feels broken |
| Items purchasable at render | 100% | A recommendation you cannot buy is not a recommendation |
| Stylist rubric score | ≥ 4.0 / 5.0 mean | Set at baseline, then held as a regression gate |
| Retrieval category precision | ≥ 0.75 on semantic queries | The agent only sees eight results; if half are the wrong garment type it cannot build an outfit |
| Retrieval recall@8 | ≥ 0.90 on known-item queries | A regression guard, not a measure of semantic quality: lexical matching alone already clears it |
| First-token latency | p95 < 2.5s | Conversational threshold; beyond it the product feels stalled |
| Cost per active user | ≤ $2.40 / month | From the unit economics in `PLAN.md` §9 |

---

## 4. Non-goals

Named explicitly so they do not accumulate as unspoken scope.

- **Mobile applications.** Web first. The shared packages make this a later addition, not a rewrite.
- **Agentic checkout.** Merchants require contemporaneous human approval before payment, and the sanctioned protocol is explicit about it. Outbound links only.
- **Design generation.** Deferred with the rest of the enterprise track.
- **Migration to AWS.** The deploy role is written and waiting. Nothing forces the move until an enterprise customer or scale requires it.
- **Fine-tuning any model.** Retrieval quality and prompting have not been exhausted; tuning before they are is premature.
- **Human stylist marketplace.** Interesting, and not on the path to proving the core product works.

---

## 5. Workstreams

Five tracks. The first three are the critical path; the fourth runs alongside and has external lead times; the fifth is deferred behind an explicit trigger.

### 5.1 Catalog Supply

Make the catalog real. This is first because everything downstream is meaningless without merchandise, and because it is the only major track with no external blocker today.

#### C1 — Storefront registry and ingestion runner

Turn the connectors into something that runs.

- A registry of storefronts to ingest: domain, retailer name, route, size-system override.
- A job that resolves the route per storefront, pages the source, normalizes, and writes through the existing write door.
- Per-run reporting: products written, offers written, quarantined by stage.

**Acceptance.** Ten storefronts ingested end to end. Quarantine rate under 5%, with every quarantined record's reason attributable to a named cause. A second run of the same storefronts changes no row counts.

**Depends on.** Nothing.

#### C2 — Catalog breadth

Reach a catalog that can dress someone.

- Expand the registry to cover the brand mix the target customer actually shops, across price tiers and categories.
- Category coverage check: no core category under-represented relative to a target assortment.

**Acceptance.** The size and brand-count targets in §3. Every core garment category populated. At least 95% of products carry a resolved category, at least 90% carry usable size data.

**Depends on.** C1.

#### C3 — Embedding service and backfill

Make search semantic rather than lexical.

- Fashion-tuned image and text embeddings behind the existing embedder interface, which search is already written against.
- Backfill over the catalog, incremental for new arrivals.
- Hosted inference initially rather than self-managed GPU; revisit when volume justifies it.

**Acceptance.** Constraint satisfaction on hand-written semantic queries, measured against the lexical-only baseline in the same run so the improvement is attributable. Vector index used by the planner, verified by query plan rather than assumed.

**Correction, 2026-09-06.** This originally called for recall@8 on a labelled
set. That was the wrong metric and it would have passed before the work started:
those queries are generated from product titles, so lexical matching already
scored 95%. Recall is still reported as a regression guard, but it does not
measure what this milestone is for. Category precision on semantic queries does,
and it moved from 20% to 79%.

**Depends on.** C2 for a corpus worth measuring against.

#### C4 — Freshness

Keep what is shown buyable.

- Re-check price and availability for anything surfaced recently.
- Verify the primary pick at render time.
- Price history retained for later sale alerts.

**Acceptance.** Dead-link target in §3, measured on a sample of surfaced items rather than the whole catalog.

**Depends on.** C1.

---

### 5.2 Styling Intelligence

The product's actual value. Evaluation is built before the agent, deliberately: what cannot be measured cannot be tuned, and a rubric written after the fact tends to describe whatever the model already does.

#### S1 — Evaluation harness

- A rubric scoring profile adherence, budget adherence, occasion fit, brand fit, item availability as a hard failure, assortment diversity, and rationale quality.
- A dataset of personas crossed with occasions, seeded from realistic briefs.
- Model-graded with a strong judge, spot-checked by hand.
- Runs in CI on any prompt, tool-schema, or model change, and blocks on regression.

**Acceptance.** Baseline recorded for a deliberately naive stylist. Judge agreement with human scoring checked on a sample. A seeded regression is caught by the gate.

**Depends on.** C1, for a catalog to recommend from.

#### S2 — Intake and style profile

- Conversational intake producing a structured profile, written through the existing write door into the profile tables.
- Extraction is a fact with provenance and confidence, never an assertion.
- Users can see and correct everything inferred about them.

**Acceptance.** Test transcripts produce valid profiles with no schema violations. Every stored preference traces to something the user said. Correction round-trips.

**Depends on.** S1.

#### S3 — Stylist agent and outfit composition

- The agent, with tools for profile, catalog search, availability, and weather.
- Outfit composition as constraint satisfaction over slots, not as free-form generation, so budget and size constraints are structurally enforced rather than requested politely.
- A rationale per outfit citing the profile facts it drew on.
- Alternates at three price points per slot.

**Acceptance.** Rubric target in §3. Every surfaced item purchasable at render. Latency target met. Cost per session inside the model in `PLAN.md` §9.

**Depends on.** S1, S2, C3.

#### S4 — Memory across sessions

- Preferences learned from behaviour, stored with provenance alongside stated ones.
- User-visible, user-editable, user-deletable.

**Acceptance.** A second session demonstrably reflects the first session's feedback. Deletion removes the memory everywhere, including any derived index.

**Depends on.** S3.

---

### 5.3 Consumer Application

#### A1 — Application shell and design system

- Tokens, components, layout primitives, dark and light.
- Accessibility built in from the first component rather than audited later.

**Acceptance.** Core flows pass WCAG 2.2 AA. Shared components live in the shared package, not the app.

**Depends on.** Nothing.

#### A2 — Intake and profile experience

**Acceptance.** A new user completes intake and sees their style profile, with every inferred trait editable.

**Depends on.** A1, S2.

#### A3 — Outfit experience

- Outfit cards, item detail, alternates, feedback.
- Affiliate and AI disclosures rendered before the first outbound click, not buried.
- Explicit "why this" surfacing the agent's rationale.

**Acceptance.** An outfit renders with live prices and working links. Disclosure is present on every surface carrying a commercial link, verified by test rather than inspection.

**Depends on.** A1, S3.

#### A4 — Accounts

- Authentication, session handling, consent capture into the existing consent ledger.

**Acceptance.** Sign-up, sign-in, sign-out, deletion. Deletion removes profile, wardrobe, memories, and derived vectors, verified end to end.

**Depends on.** A1.

#### A5 — Deployment

- Hosted on a platform whose terms permit commercial use.
- Preview deployment per pull request.
- Error tracking and structured logs reaching somewhere a human will see them.

**Acceptance.** A URL a stranger can open. Preview environments on pull requests. An induced error surfaces in tracking within a minute.

**Depends on.** A1.

---

### 5.4 Commerce and Compliance

Runs alongside the critical path. The first item has external lead time measured in weeks and should start immediately, independent of engineering progress.

#### X1 — Partner applications *(start now, not engineering-bound)*

- Affiliate network publisher accounts for coverage of department stores and larger retailers.
- A published agent profile document, which the sanctioned commerce protocol requires merchants to fetch before they will answer catalog calls.

**Acceptance.** At least one network approved. Agent profile reachable and a catalog call succeeding against a real merchant.

**Blocked by.** Approval queues, not by us.

#### X2 — Attribution and monetization

- Affiliate link decoration and click attribution.
- Subscription billing scaffolding, dormant until there is something to charge for.

**Acceptance.** A click is attributable end to end in a test transaction.

**Depends on.** X1, A3.

#### X3 — Disclosure and policy

- Affiliate material-connection disclosure before the first click, per FTC guidance.
- AI-generated content labelling and provenance for any generated imagery, per EU AI Act Article 50, adopted globally rather than gated by geography.
- Privacy policy, consent flows, and a working data-subject deletion path.

**Acceptance.** Disclosure components covered by snapshot tests. Deletion verified across every store. Counsel review before public launch.

**Depends on.** A3, A4.

#### X4 — Security readiness

- Threat model recorded.
- Tenant isolation tests, injection tests against untrusted catalog text, penetration test scheduled before enterprise general availability.

**Acceptance.** Isolation and injection suites in CI. Threat model reviewed.

**Depends on.** A5.

---

### 5.5 Enterprise Studio *(deferred)*

Half the business and deliberately not started. The consumer track proves the shared core, the catalog, and the styling engine, all of which the enterprise product reuses. Building both at once with the current team would slow both.

**Trigger to start.** A signed design partner, or the consumer demo reaching its §3 targets, whichever comes first.

Outline, so the shape is not lost:

| Milestone | Scope |
|---|---|
| E1 | Tenant onboarding, single sign-on, per-tenant isolation and keys |
| E2 | Brand knowledge ingestion from lookbooks and line sheets into brand codes with evidence |
| E3 | Trend corpus and attribute time series, from licensed runway data, platform APIs, and owned assortment analytics |
| E4 | Trend reports with citations, numbers computed in the database rather than by a model |
| E5 | Concept generation, iteration tooling, and an intellectual-property critic |
| E6 | Authorship records and exports to product lifecycle management systems |

**Note on cost.** The trend corpus carries a data licensing line item that has not been committed to. That decision gates E3 and should be made before E1 starts, not during.

---

## 6. Sequencing

```
        now                                                      demo ready
         │                                                            │
  C1 ────┼────► C2 ────► C3 ────────────────► C4                      │
         │                        │                                   │
  S1 ────┼──────────────► S2 ────►┼─► S3 ──────────► S4               │
         │                        │    │                              │
  A1 ────┼────► A2 ──────────────►┼───►┼─► A3 ─► A4 ─► A5 ────────────┤
         │                        │    │                              │
  X1 ════╪════════════════════════╪════╪══► X2 ─► X3 ─► X4            │
         │  (external queue)      │    │                              │
```

**Critical path.** `C1 → C2 → C3 → S3 → A3 → A5`. Everything else has slack.

**Parallelism.** The application shell and the evaluation harness need nothing and can start on day one alongside catalog work. Partner applications are pure calendar time and should be filed immediately.

**Staffing.** Written for one engineer working with an AI pair. Two engineers would let the application track run genuinely parallel to catalog and styling, compressing the calendar by roughly a third. The plan does not assume that.

**Stage gates.** Each track exits only on its acceptance criteria. The temptation worth naming: starting the application before the catalog is real produces a convincing demo of an empty product, which teaches you nothing and is expensive to unwind.

---

## 7. Risk register

| # | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| R1 | Catalog coverage too thin for credible outfits | High | Medium | Measure breadth at C1 before building on it. Sanctioned protocol adoption looked universal on sampled storefronts, which is encouraging but was a small sample |
| R2 | Affiliate applications rejected for lack of traffic | High | Medium | Classic chicken-and-egg. File early, lead with platform-native and aggregator routes that do not gate on volume |
| R3 | Stylist quality plateaus below the rubric target | High | Medium | Evaluation first, so the plateau is visible early. Retrieval quality is the usual culprit before prompting is |
| R4 | Model spend exceeds the unit economics | Medium | Medium | Per-call cost attribution already exists. Enforce per-session budgets and cache aggressively before considering a cheaper model |
| R5 | A storefront changes shape and ingestion degrades quietly | Medium | High | Quarantine already makes this visible as a number. Alert on the rate, not just record it |
| R6 | Legal exposure from undisclosed commercial links or unlabelled AI content | High | Low | X3 is on the critical path to public launch, not after it |
| R7 | Solo-developer concentration risk | High | Medium | Everything is committed, reviewed by CI, and documented. The principles file exists so a second engineer is productive without archaeology |
| R8 | Enterprise track never starts because consumer work expands | Medium | High | The trigger in §5.5 is written down precisely so this decision is deliberate |

---

## 8. Open decisions

| # | Decision | Needed by | Default if unanswered |
|---|---|---|---|
| D1 | Hosting platform for the web application | A5 | The one whose free tier permits commercial use |
| D2 | Embedding inference: hosted API or self-managed | C3 | Hosted, revisit at volume |
| D3 | Whether product images are copied to our own storage or hot-linked | C2 | Hot-link for the demo, copy when links start rotting |
| D4 | Authentication provider | A4 | The one already bundled with the database platform, unless enterprise single sign-on lands first |
| D5 | Data licensing budget for the trend corpus | Before E1 | Enterprise track does not start |
| D6 | Target customer segment sharp enough to pick the brand mix | C2 | Contemporary womenswear, as the plan assumes |

---

## 9. Definition of done

Applies to every milestone, extending the pre-ship checklist in `CLAUDE.md`.

- Acceptance criteria met and demonstrated against a running system, not argued from a diff.
- Tests covering the behaviour, including the failure modes, not only the happy path.
- Lint, strict typing, and the full test suite green in continuous integration.
- One migration head, applying cleanly from empty, with no model drift.
- Every new definition reachable from something that actually runs.
- Any claim of the form "this is fast" or "this is correct" backed by a measurement recorded in the pull request.
- User-facing changes carry their disclosures.

---

## Appendix A — What exists today

| Component | State |
|---|---|
| Data model and migrations | 21 tables, applied to local and hosted databases, no drift |
| GraphQL API | Generated from the model graph; selection-driven loading with query counts asserted |
| Write path | One mutation over an upsert writer keyed on natural constraints |
| Model gateway | Three platforms, route-based model selection, per-call cost from reported usage |
| Catalog boundary | Currency, colour and size normalization; three connectors; quarantine for malformed records |
| Search | Hybrid vector and lexical with rank fusion; filters enforced as hard constraints |
| Infrastructure code | Deploy role written, nothing deployed |
| Continuous integration | Eight gates including migration drift and dead-code detection |
| Hosted database | Live, migrated, verified |
