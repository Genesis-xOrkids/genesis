---
title: Model tiering
type: decision
sources: [PLAN.md, CLAUDE.md]
related: ["[[model-platform]]", "[[prompt-caching]]", "[[unit-economics]]", "[[evals-as-gates]]", "[[provider-agnostic-intelligence]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## The decision

Three models, assigned by workload rather than by preference (PLAN.md §1 decision
3, §4.2; CLAUDE.md, Agents).

| Workload | Model | $/MTok in / out (cache read) |
|---|---|---|
| Agent turns, outfit reasoning, B2B synthesis, concept direction | **Claude Opus 5** | $5 / $25 ($0.50) |
| Same, cost-optimized — **only on eval parity** | Claude Sonnet 5 | $2 / $10 ($0.20), permanent |
| Attribute extraction, classification, dedupe, size-chart parsing | **Claude Haiku 4.5** | $1 / $5 ($0.10); batch $0.50 / $2.50 |
| IP adjudication, monthly executive memo | Opus 5 at `effort: xhigh` (Fable 5.1 optional, $10/$50) | — |

## The rule that decides it

**"Per-task cost, not per-token, decides"** (PLAN.md §4.2). An Opus turn that
resolves a constraint in one pass can be cheaper than three Sonnet turns that do
not — and CLAUDE.md turns this into a hard gate: Sonnet 5 is used *only when evals
show parity*. Price alone never justifies a downgrade ([[evals-as-gates]]).

Haiku's placement is volume, not simplicity: millions of product and wardrobe
images at ~1,600 tokens per 1024² image, run in batch at 50% off. That single
line is ≈ $1,500/month against ≈ $3,000 unbatched ([[unit-economics]]).

## The settings that come with it

- **Adaptive thinking is the default. Never set `budget_tokens`.**
- Tune `output_config.effort` per route: `medium` for chat, `high` for reports,
  `xhigh` only for IP adjudication.
- **Never prefill assistant turns.**
- Measure before adding model cascades: one model keeps one cache namespace, and
  cache fragmentation can cost more than the cascade saves ([[prompt-caching]]).

## The tokenizer footnote that changes budgets

Claude 4.7+ models produce roughly **30% more tokens than Sonnet 4.6-era models
for the same text** (PLAN.md §4.2). Any cost estimate carried over from an earlier
model generation is low by about a third.
