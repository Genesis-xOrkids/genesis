---
title: One write door
type: concept
sources: [CLAUDE.md]
related: ["[[database-is-the-api]]", "[[provenance-creates-rows]]", "[[source-agnostic-core]]", "[[no-silent-fallbacks]]", "[[engineering-constitution]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

A single generic mutation, `writeData`, takes entity targets plus named field
writes. "Save profile", "add to capsule", "approve concept" are payload shapes,
not endpoints — the intent lives in the client. Agents and pipelines write through
the same door via the same `write_specs` (CLAUDE.md, API).

## Why one door rather than a mutation per action

The stated reason is a complexity count: a mutation per action recreates the
`O(fields × sources)` sprawl that the one-write-path principle exists to kill.
With five sources writing a preference — intake, behavioural inference, user edit,
stylist annotation, document extraction — a per-action API grows a write path per
pair. One door grows none.

The corresponding data-side rule: **one write path per fact**. After boundary
translation ([[source-agnostic-core]]), every source writes through the same
writer into the same canonical representation. No source gets a bespoke column or
a parallel writer, inputs describing one concept converge on one row, and the
latest write wins.

## Idempotency is part of the door

Writes upsert on natural keys, so a re-sync never creates duplicates:

| Entity | Natural key |
|---|---|
| Products, offers | `(source, source_id)` |
| Observations | `(source, external_id)` |
| Brand documents | `(tenant_id, s3_key)` |

Constraints are named in `__table_args__`: `unique_{table}_{columns}`,
`ix_{table}_{columns}`.

## What it does not do

It does not absorb malformed input. A record that fails validation is quarantined
with its error, not defaulted through the door — see [[no-silent-fallbacks]].

## Status

Built. ROADMAP.md App. A: "One mutation over an upsert writer keyed on natural
constraints". Implementation in `api/genesis_api/writer/`, tested in
`api/tests/test_writer.py`.
