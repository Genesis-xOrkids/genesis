---
title: Index
type: entity
sources: [PLAN.md, ROADMAP.md, CLAUDE.md, README.md]
related: ["[[log]]"]
created: 2026-09-07
last-updated: 2026-09-12
---

The catalog of every page in this wiki. Compiled from `raw/` by `/brain:ingest`
against the schema in `../CLAUDE.md`.

**Start here**: [[current-state]] for what exists and what done means,
[[roadmap]] for the delivery order, [[plan]] for why the architecture is shaped
this way, [[engineering-constitution]] for how anything gets built.

---

## Sources

One summary per source document. The documents themselves stay in the repository
root and are read there; `raw/repo-docs/` holds pointers, not copies.

- [[plan]] — PLAN.md: the founding architecture and research, and the ten decisions that carry it
- [[roadmap]] — ROADMAP.md: what is next, in what order, measured not recalled
- [[engineering-constitution]] — CLAUDE.md: how the project designs, models, writes, ships and reviews
- [[readme]] — README.md: how to run it, and the only place the real database and model defaults are written down

## Projects

- [[current-state]] — what is built, the eight success targets, the six non-goals, the critical path
- [[catalog-supply]] — C1–C4: make the catalog real. C1 and C3 done, C2 stalled short of target
- [[styling-intelligence]] — S1–S4: the product's actual value. Evaluation first, agent second. Nothing built
- [[consumer-application]] — A1–A5: the half a stranger can open. Nothing built
- [[commerce-and-compliance]] — X1–X4: affiliate approvals, attribution, disclosure, security readiness
- [[enterprise-studio]] — E1–E6: half the business, deferred behind a written trigger
- [[risk-register]] — eight risks; the two rated high-likelihood fail in opposite ways

## Decisions

- [[model-platform]] — three paths to Claude behind one gateway; plan and practice disagree on the default
- [[model-tiering]] — Opus for judgment, Haiku for volume, Sonnet only on eval parity
- [[agent-runtime]] — AgentCore and Strands, and why model-agnostic hosting matters
- [[catalog-sources]] — layered sanctioned sources, no scraping, and why Amazon is deferred
- [[embeddings-and-vectors]] — FashionSigLIP in pgvector, and the 30× cost gap that was accepted on purpose
- [[image-generation]] — the Stability suite, and the AWS default that dies 2026-09-30
- [[database-choice]] — Aurora planned, Neon in use, Alembic owning the schema
- [[agent-network]] — the employees that work on this repository, how tasks reach them, and where their runs are recorded
- [[open-decisions]] — six decisions with written defaults, plus the `[verify]` list

## Concepts

**Architecture**

- [[two-planes-one-monorepo]] — TypeScript product plane, Python intelligence plane, three contracts between them
- [[database-is-the-api]] — models are the schema; no DTOs, no hand-written resolvers, no N+1
- [[one-write-door]] — one generic mutation, one write path per fact, idempotent on natural keys
- [[source-agnostic-core]] — every source translated at the boundary; a merchandiser's facet is not a fact
- [[provider-agnostic-intelligence]] — one `ModelGateway`; the identical-request-body test is what makes it real

**Data discipline**

- [[atomic-facts-not-derivations]] — decompose shorthand, never store an interpretation
- [[provenance-creates-rows]] — origin is a value in a `source` column, never a parallel column
- [[null-means-unknown]] — null is never false, zero or empty, and the UI stays conservative
- [[no-silent-fallbacks]] — quarantine with the error instead of defaulting; alert on the rate

**Intelligence**

- [[hybrid-catalog-search]] — vector + filters + full-text rank, eight results with at most two colourways per style, and a browse order that is not price
- [[fashion-taxonomy]] — Fashionpedia plus a silhouette vocabulary; enums for closed sets, tables for open ones
- [[prompt-caching]] — stable prefix, volatile tail, and the three silent invalidators
- [[tool-results-are-data]] — retrieved text is untrusted; write tools are gated; numbers come from SQL
- [[evals-as-gates]] — a prompt edit without an eval run is not done
- [[trend-corpus]] — six legitimate layers, because there is no social firehose to have

**Operations**

- [[image-provenance]] — C2PA, watermark, label, lineage row; an image without lineage does not leave
- [[tenant-isolation]] — four stores to isolate, and a failing test is a release blocker
- [[unit-economics]] — ≤ $2.40/user/month, and the levers in the order they should be pulled
- [[pre-ship-checklist]] — the half CI enforces, and the half only a grep can

## People

None. The sources name no individuals — [[roadmap]] §6 describes the team as one
engineer with an AI pair. See `people/README.md`.
