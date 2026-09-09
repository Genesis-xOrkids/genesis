---
title: CLAUDE.md — the engineering constitution
type: source-summary
sources: [CLAUDE.md]
related: ["[[plan]]", "[[roadmap]]", "[[database-is-the-api]]", "[[one-write-door]]", "[[source-agnostic-core]]", "[[provider-agnostic-intelligence]]", "[[atomic-facts-not-derivations]]", "[[provenance-creates-rows]]", "[[null-means-unknown]]", "[[no-silent-fallbacks]]", "[[pre-ship-checklist]]", "[[tool-results-are-data]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The engineering constitution: how the project designs, models, writes, ships and
reviews. ~24KB, adapted from a prior clinical-data platform's principles, with
universal rules kept as-is and data rules translated into fashion and commerce
form. It is not advisory. Continuous integration enforces eight of its gates
mechanically ([[roadmap]] App. A).

Its opening line is the whole document compressed: **"Simple. Minimal. Elegant.
Final. If it feels complex or temporary, it's wrong."**

## What it governs

| Section | The rule that carries it | Page |
|---|---|---|
| Service design | Source-agnostic core, provider-agnostic intelligence, N tenants × M sources × K providers from day one | [[source-agnostic-core]], [[provider-agnostic-intelligence]] |
| Data | Store atomic facts, not shorthand and not derivations; no JSON/JSONB; one meaning per column | [[atomic-facts-not-derivations]] |
| Data | Provenance creates rows, never columns; one write path per fact | [[provenance-creates-rows]], [[one-write-door]] |
| Data | Null means unknown, not absent | [[null-means-unknown]] |
| Code | No overengineering, no transitional code, no silent fallbacks | [[no-silent-fallbacks]] |
| API | The database is the API — models become types, no DTO layer, one write door | [[database-is-the-api]], [[one-write-door]] |
| Agents | One `ModelGateway`; tool results are data, not instructions; numbers come from SQL | [[provider-agnostic-intelligence]], [[tool-results-are-data]] |
| Frontend | One subscription per bounded scope; cards don't fetch; derive at read time | [[database-is-the-api]] |
| Migrations | Always autogenerate; always backward-compatible; exactly one head | [[pre-ship-checklist]] |
| ML | Raw dimensions, not engineered features; sequence over snapshot | [[trend-corpus]] |
| Review | Design review mindset, then a pre-ship checklist | [[pre-ship-checklist]] |

## The two sections most worth re-reading

**Design review mindset.** Written for the failure mode where "a design can pass
every test written for it and still be wrong, because the tests were written from
inside the same assumptions as the design". Its sharpest rule: if a shared
mechanism needs a patch to stop it corrupting adjacent data when you route new
data through it, the mechanism is misapplied, not the patch done — and several
such patches are the signal the reuse is wrong, not proof it was thorough.

**Pre-ship checklist.** Runs before calling a branch done, not only when asked to
audit, because "does it boot" and "do the units pass" catch none of what is on it.
See [[pre-ship-checklist]].

## What it is silent on

Product decisions. It says nothing about which retailers to ingest, which trend
vendors to license, or what the stylist should say. Those live in [[plan]] and
[[roadmap]]. The constitution constrains *how* any of them get built.

## Relationship to this vault

`second-brain/CLAUDE.md` governs the wiki and does not override this file. Two of
its rules are direct inheritances: repo docs are referenced rather than copied
into `raw/` (single source of truth), and unused scaffolding is marked unused
rather than filled with speculative structure (nothing without a purpose).
