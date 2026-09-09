---
title: Where agents run — AgentCore and Strands
type: decision
sources: [PLAN.md]
related: ["[[model-platform]]", "[[tool-results-are-data]]", "[[styling-intelligence]]", "[[tenant-isolation]]", "[[two-planes-one-monorepo]]", "[[unit-economics]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## The decision

Agents are written with the **Strands Agents SDK** (Python) and hosted on **Amazon
Bedrock AgentCore** — Runtime, Memory, Gateway, Identity, Policy and Evaluations
(PLAN.md §1 decision 1, §4.3).

## What each AgentCore component is load-bearing for

| Component | Why it is in the design |
|---|---|
| **Runtime** | Per-session microVM isolation — isolated compute, memory and filesystem, sanitized on termination — with sessions up to 8 hours |
| **Gateway** | Internal tools exposed as MCP tools (Lambda or OpenAPI targets), which is one of the three contracts between the planes ([[two-planes-one-monorepo]]) |
| **Identity** | Native OAuth 2.0 to third parties — Shopify, Instagram Graph, Pinterest — so a brand connects its own account rather than us holding credentials |
| **Policy** | Cedar authorization per tool call against the user's entitlements ([[tool-results-are-data]]) |
| **Memory** | User-preference, semantic and episodic strategies, namespaced per user and tenant |

Billing is consumption-based on active time only: $0.0895/vCPU-h, $0.00945/GB-h,
which is ≈ $0.10/user/month at ~20 minutes active ([[unit-economics]]).

## Why model-agnostic hosting matters here

AgentCore is model-agnostic, so the [[model-platform]] choice stays independent of
the runtime choice. Changing where Claude is served does not change where the
agent runs, and vice versa. That is the same separation [[provider-agnostic-intelligence]]
enforces one layer down.

## The orchestration shape

A thin supervisor per product surface — B2C "Stylist", B2B "Studio" — delegates to
specialists using Strands multi-agent primitives (agent-as-tool, swarm, graph), or
A2A for cross-runtime calls. **The supervisor's system prompt and tool list stay
stable** so the cache prefix survives delegation; volatile context arrives after
the breakpoint or as mid-conversation system messages ([[prompt-caching]]).

## Alternatives considered

- **Strands TypeScript 1.0** (2026-04-30) for any tool that must live in the
  product plane.
- **Anthropic Tool Runner with an own loop on Fargate.**
- **Claude Managed Agents**, available on Claude Platform on AWS only.
- **AgentCore Harness** (GA 2026-06-17), which can replace hand-written loops for
  simple agents via `CreateHarness` / `InvokeHarness`.

## The memory hedge

Long-term memory lives in AgentCore Memory, but **critical facts are mirrored into
Postgres so the product does not depend on a single vendor's memory store**
(PLAN.md §4.3). The same reasoning as every other adapter in the system, applied
to the one component that holds irreplaceable user state.

## Status

Not built. `intelligence/agents/stylist/` and `intelligence/agents/studio/` are
empty directories; the agent work is [[styling-intelligence]] S3.
