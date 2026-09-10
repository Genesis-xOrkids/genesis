---
title: Tenant isolation is an operational property
type: concept
sources: [CLAUDE.md, PLAN.md, ROADMAP.md]
related: ["[[tool-results-are-data]]", "[[enterprise-studio]]", "[[two-planes-one-monorepo]]", "[[commerce-and-compliance]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

Per-tenant keys, indexes, memory stores and cost attribution. **A failing isolation
test is a release blocker** (CLAUDE.md, Operations).

Stated as an operational property rather than a design goal on purpose: it is not
enough for the architecture to permit isolation, it has to be continuously tested,
and the test failing stops a release.

## The layers it has to hold at

PLAN.md §6.2 lists them, and they are separate mechanisms rather than one:

| Layer | Isolation mechanism |
|---|---|
| Storage | Separate S3 prefixes **and separate KMS keys** per tenant |
| Database | Postgres row-level security keyed by tenant |
| Vectors | Separate vector indexes per tenant |
| Agent memory | Separate AgentCore Memory stores, namespaced per tenant |
| Identity | RBAC with tenant claims in tokens |
| Cost | Per-tenant attribution and monthly caps enforced at the API layer |

Plus a contractual and technical guarantee of **no cross-tenant training or
retrieval**, and an optional dedicated AWS account for the largest customers.

## Why the stakes are higher here than in most multi-tenant products

B2B brand data is trade-secret grade: lookbooks, unreleased line sheets, PLM
exports, and a stylist team's private annotations on unreleased concepts. A
cross-tenant leak is not an embarrassment, it is a competitor seeing next season.

## How it is verified

Automated IDOR and tenant-isolation tests asserting that tenant A cannot retrieve
tenant B's **rows, vectors, memories, or S3 objects** (PLAN.md §12) — four stores,
because isolating the database and forgetting the vector index is the obvious
failure. Plus SSRF tests on URL tools, and an external penetration test before B2B
general availability (ROADMAP.md §5.4 X4).

## Status

Foundational only. ROADMAP.md §2 lists "the entire enterprise studio beyond a
tenant table" as not built. The isolation suite is X4, which depends on A5
(deployment) and has not started.
