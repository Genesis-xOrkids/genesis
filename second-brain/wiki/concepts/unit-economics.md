---
title: Unit economics
type: concept
sources: [PLAN.md, ROADMAP.md]
related: ["[[model-tiering]]", "[[prompt-caching]]", "[[provider-agnostic-intelligence]]", "[[evals-as-gates]]", "[[catalog-sources]]", "[[risk-register]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The cost model at list prices, September 2026 (PLAN.md §9), and the target it
produces: **≤ $2.40 per active user per month** (ROADMAP.md §3).

## Consumer, per active user per month

Modelled at four sessions × eight turns, with ~6K cached tokens of system prompt,
tools and profile, 1.5K new input, 3K tool results and 800 output per turn.

| | Opus 5 | Sonnet 5 |
|---|---|---|
| Per turn | ≈ $0.046 | ≈ $0.018 |
| Per session (8 turns) | ≈ $0.37 | ≈ $0.15 |
| Model, per month | ≈ $1.47 | ≈ $0.58 |
| Lookbook images (2/session) | ≈ $0.32–0.64 | same |
| Try-on (2/month) | $0.15 | same |
| AgentCore runtime + memory | ≈ $0.10 | same |
| **Steady-state COGS** | **≈ $2.0–2.4** | **≈ $1.1–1.5** |

A $12–20/month subscription clears this comfortably, as does a free tier funded by
affiliate revenue at a typical 5–15% of order value.

## The one-time cost that breaks the model

**Wardrobe onboarding: ≈ $2.15 per user** — 50 items at Haiku extraction ≈ $0.003
plus background removal ≈ $0.04 each. Nearly a full month of steady-state COGS,
paid before the user has paid anything. PLAN.md's response is to gate it behind
the paid tier or amortize it through batch pricing at 50% off.

Worth noting because it is the only line where a *product* decision (offer closet
digitization to free users?) is really a unit-economics decision.

## Pipelines, monthly and illustrative

| Job | Volume | Cost |
|---|---|---|
| Product attribute extraction (Haiku 4.5, batch) | 1M images | ≈ $1,500 (≈ $3,000 unbatched) |
| Embeddings (self-hosted FashionSigLIP GPU) | 1M images | ≈ $3 — or $100 on Nova MM |
| Trend corpus extraction | 300K images | ≈ $450 batched |
| B2B report synthesis (Opus 5) | 200 reports | ≈ $90 |
| Concept generation | 2,000 concepts | ≈ $1,100–2,200 |
| Aurora Serverless v2 prod (≈4 ACU avg) | — | ≈ $700 |

The embeddings row is the striking one: self-hosting FashionSigLIP costs ~$3 per
million images against ~$100 managed, a 30× gap. See [[embeddings-and-vectors]].

Fixed platform baseline before scale: ≈ $1.5–3K/month, **plus data licences —
named as the single largest discretionary line item**. See [[trend-corpus]].

## The levers, in the order they should be pulled

PLAN.md §4.7: caching first ([[prompt-caching]]), then effort tuning, then batch
everything offline, right-size images, retrieve small, context hygiene, token
budgets and kill switches, quota planning — and **evals as the gate for any
downgrade** ([[evals-as-gates]]).

The ordering is the content. Switching to a cheaper model is not on the list until
the eight cheaper-and-free levers are exhausted, and even then only on eval parity.
Risk R4 says it directly: "enforce per-session budgets and cache aggressively
before considering a cheaper model" (ROADMAP.md §7).

## What makes any of this enforceable

Per-call cost attribution already exists in the [[provider-agnostic-intelligence]]
gateway. Without it these numbers would be projections rather than a budget.
