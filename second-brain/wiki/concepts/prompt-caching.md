---
title: Stable prefix, volatile tail
type: concept
sources: [CLAUDE.md, PLAN.md]
related: ["[[provider-agnostic-intelligence]]", "[[model-tiering]]", "[[unit-economics]]", "[[evals-as-gates]]", "[[tool-results-are-data]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The system prompt and tool schemas are frozen and cached; per-request facts —
date, weather, session state — come *after* the last cache breakpoint or arrive as
mid-conversation system messages. **CI asserts `cache_read_input_tokens > 0` on
the second call** (CLAUDE.md, Agents).

PLAN.md §4.7 lists prompt caching as efficiency lever number one, ahead of effort
tuning, batching, and every other option.

## The mechanics

- Freeze the stylist system prompt, tool schemas and rubric together as one
  prefix. Minimums: ≥1,024 tokens on Sonnet 5, ≥4,096 on Haiku 4.5 for the Bedrock
  path. Four checkpoints available, 5-minute or 1-hour TTL; use the 1-hour TTL for
  session-long reuse.
- Put the user profile at the **second** breakpoint, so a profile edit does not
  invalidate the shared prefix.
- Keep the supervisor's system prompt and tool list stable across specialists
  (PLAN.md §4.3), so delegating does not cost a cache namespace.

## The silent invalidators

Named and banned (PLAN.md §4.7): **timestamps in the system prompt, unsorted tool
lists, per-request IDs before the breakpoint.** Each is invisible in a diff and
each turns every call into a cache miss. This is why the CI assertion exists —
a broken cache does not fail anything, it just quietly triples the bill.

## What it buys

At the modelled usage — 6K cached tokens of system, tools and profile per turn —
cache reads cost $0.003 per turn on Opus 5 against $0.0225 for 4.5K of new input.
Roughly a tenth the rate for the largest stable block in the request. See
[[unit-economics]].

## The related model rules

From CLAUDE.md, Agents, and reinforced in PLAN.md §4.2:

- **Adaptive thinking is the default. Never set `budget_tokens`.**
- Tune `output_config.effort` per route instead: `medium` for chat turns, `high`
  for reports, `xhigh` only for IP adjudication.
- **Never prefill assistant turns.**
- Measure before adding model cascades — one model keeps one cache namespace
  (PLAN.md §4.7 lever 2). A cascade that saves per-token can lose more to cache
  fragmentation than it saves.

Tokenizer note carried from PLAN.md §4.2: Claude 4.7+ models produce roughly 30%
more tokens than Sonnet 4.6-era models for the same text. Budget accordingly.
