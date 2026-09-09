---
title: The database is the API
type: concept
sources: [CLAUDE.md, PLAN.md]
related: ["[[one-write-door]]", "[[two-planes-one-monorepo]]", "[[atomic-facts-not-derivations]]", "[[null-means-unknown]]", "[[engineering-constitution]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The frontend gets fast, unfettered access to the database through GraphQL, and the
backend does not redefine what the database already defines. SQLAlchemy models
*are* the schema: models become types, relationships become fields, the selection
set drives loading. Add a model, get an API. No intermediate service layer, no
DTOs, no hand-written resolvers for standard data access (CLAUDE.md, API).

TypeScript types are generated from the GraphQL schema, never hand-written.

## The rules that make it hold

- **Read path is Core, write path is ORM.** Strawberry types are built directly
  from Core row dicts; the ORM stays canonical for writes, schema authority and
  Alembic autogenerate. The two halves share the schema, not the execution model.
- **Every FK the API traverses gets a relationship declaration.** A missing one is
  a *startup* error, not a runtime warning. `viewonly=True` is the right shape
  when the parent-side traversal is query-only.
- **Every GraphQL-traversed table has an integer `id` primary key**, including
  reference and vocabulary tables that already have a natural key. A FK pointing at
  a non-`id` column passes type building and throws at query time.
- **Selection-driven loading at any depth**: one query per requested relationship,
  never more. No dataloaders on the eager path, no N+1, no per-query configuration.
- **Resolve before yield.** Convert to plain Strawberry types inside the session,
  close it, then yield. No ORM or Core access during serialization.
- **Generated, not written**: types, dataloaders, resolvers and subscription
  channels all derive from the model graph. Only computed fields are hand-written.

## Where the line sits on computed fields

Computed fields may complete an *atomic* value the source omitted (a normalized
`price_usd_cents`, `color_family` from hex) or expose a value the backend itself
needs for alerting, ML features or server-side filtering. They may not carry
interpretations: `is_on_sale`, `is_in_capsule`, latest price and trend direction
are derived on the frontend, at read time, from stored facts. This is the same
line drawn in [[atomic-facts-not-derivations]], applied one layer up.

## Streams versus queries

Bounded scopes stream; unbounded sets query. A user's workspace (profile,
wardrobe, outfits, memories) and a brand board are bounded and subscribed. The
catalog, the trend corpus and price history are unbounded and reached by HTTP
query with args, on demand. Subscription child fields take no `where`/`orderBy`/
`limit` args at all — they would bypass eager loading and force dataloaders — so
subscriptions load everything for a bounded scope and the client filters.

Subscriptions yield lists, never individual items: each yield is a full execution
cycle, so N items is N cycles where one list is one.

## Status

Built. ROADMAP.md App. A: "Generated from the model graph; selection-driven
loading with query counts asserted". The generator lives in
`api/genesis_api/graphql/` (`type_builder.py`, `loader.py`, `registry.py`,
`schema.py`).
