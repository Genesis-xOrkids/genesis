---
title: Null means unknown, not absent
type: concept
sources: [CLAUDE.md]
related: ["[[no-silent-fallbacks]]", "[[atomic-facts-not-derivations]]", "[[provenance-creates-rows]]", "[[database-is-the-api]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

Null carries one meaning — *we do not know* — and never stands in for false, zero
or empty (CLAUDE.md, Data):

- `sale_price_usd_cents = null` is "we don't know", not "no sale".
- `in_stock = null` is unknown; `false` is *known* out of stock.
- `wear_count = 0` is a known zero.

## It has to hold through the whole stack

A nullable column is `T | null` in TypeScript, the mapper preserves the null, and
the component decides how to render unknown — a dash, a fallback label, a hidden
section. Never coerce null to `""`, `0` or `false` in the data layer (CLAUDE.md,
Frontend). A coercion anywhere in the chain destroys the distinction permanently,
because nothing downstream can tell a real zero from a filled-in one.

## Stakes-asymmetric booleans

The rule that makes this a safety property rather than a modelling preference.
Where being wrong in one direction costs more than the other, the UI requires
explicit confirmation and treats null as the conservative case (CLAUDE.md,
Frontend):

| Show | Only when | Because null would otherwise |
|---|---|---|
| "Buy" | `purchasable === true` | offer a purchase that fails |
| "In stock" | `in_stock === true` | promise stock that isn't there |
| Human-made (no AI label) | `human_made === true` | ship an unlabelled AI image — see [[image-provenance]] |
| Concept export | `ip_reviewed === true` | export unreviewed IP |

Note the third row's direction: the *label* is the safe default, so an image is
treated as AI-generated unless provenance says otherwise. That is a legal
requirement, not a preference (EU AI Act Art. 50, PLAN.md §7).

## The related frontend rule

**Fix the data flow, don't remove the UI.** A blank field means a missing source
or mapping; the response is to wire up the real derivation or sync, not to delete
the display. Removing it hides the problem from audit (CLAUDE.md, Frontend).
