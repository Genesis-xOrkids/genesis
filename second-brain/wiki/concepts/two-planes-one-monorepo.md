---
title: Two planes, one monorepo
type: concept
sources: [PLAN.md, CLAUDE.md]
related: ["[[database-is-the-api]]", "[[provider-agnostic-intelligence]]", "[[source-agnostic-core]]", "[[plan]]", "[[engineering-constitution]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The repository is split into two language planes that ship independently and meet
only at declared contracts (PLAN.md §1 decision 8).

- **Product plane, TypeScript.** `apps/web` (Next.js 16, both the B2C app and the
  B2B Studio console), `apps/mobile` (Expo, Phase 2), `packages/ui` (shared
  components), `packages/domain` (shared derivations).
- **Intelligence plane, Python.** `api/` (Strawberry GraphQL generated from
  SQLAlchemy models), `intelligence/agents/*` (Strands agents on AgentCore),
  `intelligence/pipelines/`, `intelligence/model_gateway/`,
  `intelligence/catalog/`, `intelligence/imagery/`, `intelligence/guardrails/`,
  `services/embeddings/`.

## Why the split, rather than one language

Each plane is chosen where it is first-class. Python is the first-class path for
Strands, the AgentCore SDK, FashionSigLIP and PyTorch, dataframe-style trend
analytics, and C2PA tooling. TypeScript is the first-class path for Next.js, Expo
and type-safe product APIs. The stated reason for not forcing one side into the
other's language: *that is where AI platforms accumulate brittle glue*
(PLAN.md §1).

## The three contracts

Planes never talk through a shared table reached from two codebases
(CLAUDE.md, Service design). They talk through:

1. **The generated GraphQL schema** — SDL from the SQLAlchemy model graph,
   TypeScript types from it via graphql-codegen, CI failing on drift. See
   [[database-is-the-api]].
2. **MCP tool schemas** via AgentCore Gateway, for anything an agent calls.
3. **Versioned events** on EventBridge with a schema registry.

## Why it matters beyond tidiness

The three scale axes in CLAUDE.md — N brand tenants, M data sources, K model and
image providers — all live in the intelligence plane. Keeping the product plane
behind a schema contract means adding a connector, an agent, or a model provider
never touches product code. Anything that works for exactly one tenant, source or
provider is called a prototype, not a design.

## Status

Real, partially. The Python plane exists and is substantial: `api/`,
`intelligence/`, `services/embeddings/`, `evals/`. The TypeScript plane is
scaffolding — `apps/` and `packages/` are empty directories, because
[[consumer-application]] A1 has not started (ROADMAP.md §2: zero deployed
user-facing surfaces).
