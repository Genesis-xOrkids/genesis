---
title: Consumer Application (A1–A5)
type: project
sources: [ROADMAP.md, PLAN.md]
related: ["[[current-state]]", "[[two-planes-one-monorepo]]", "[[styling-intelligence]]", "[[commerce-and-compliance]]", "[[null-means-unknown]]", "[[database-is-the-api]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The half of the product a stranger can open. Nothing in it is built: zero deployed
user-facing surfaces as of 2026-09-05, and `apps/` and `packages/` are empty
directories.

## A1 — Application shell and design system ⬜

Tokens, components, layout primitives, dark and light. **Accessibility built in
from the first component rather than audited later** — WCAG 2.2 AA on core flows,
with the European Accessibility Act as the other driver (PLAN.md §7).

Shared components live in `packages/ui`, not in the app ([[two-planes-one-monorepo]]).

Depends on nothing. Can start on day one, in parallel with catalog work.

## A2 — Intake and profile experience ⬜

Acceptance: a new user completes intake and sees their style profile, **with every
inferred trait editable**. Depends on A1 and S2.

## A3 — Outfit experience ⬜ *(critical path)*

Outfit cards, item detail, alternates, feedback, and an explicit "why this"
surfacing the agent's rationale.

**Affiliate and AI disclosures render before the first outbound click, not buried.**
Acceptance requires disclosure to be present on every surface carrying a commercial
link, *verified by test rather than inspection* — see [[commerce-and-compliance]].

The frontend rules this track is written against (CLAUDE.md, Frontend): cards
don't fetch; one subscription per bounded scope with a shared Map; derive at read
time and cache nothing; null stays unknown through the whole stack
([[null-means-unknown]]); stakes-asymmetric booleans require explicit confirmation,
so "Buy" appears only when `purchasable === true`.

Depends on A1 and S3.

## A4 — Accounts ⬜

Authentication, session handling, consent capture into the existing consent ledger.

Acceptance: sign-up, sign-in, sign-out, deletion — where **deletion removes
profile, wardrobe, memories, and derived vectors, verified end to end**. Same
shape as S4's deletion requirement, and the same hard part.

Depends on A1. Auth provider is open decision D4.

## A5 — Deployment ⬜ *(critical path, terminal)*

Hosted on a platform whose terms permit commercial use, with a preview deployment
per pull request and error tracking plus structured logs reaching somewhere a
human will see them.

Acceptance: **a URL a stranger can open**, preview environments on pull requests,
and an induced error surfacing in tracking within a minute.

Depends on A1. Hosting platform is open decision D1; migration to AWS is a
non-goal, so the CDK deploy role stays written and unused until an enterprise
customer or scale forces the move.
