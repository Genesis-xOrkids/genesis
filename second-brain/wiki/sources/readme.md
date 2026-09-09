---
title: README.md — how to run it
type: source-summary
sources: [README.md]
related: ["[[plan]]", "[[roadmap]]", "[[engineering-constitution]]", "[[database-choice]]", "[[model-platform]]", "[[pre-ship-checklist]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The operational front door: what the project is in three lines, which of the three
documents does what job, and the commands to get a working local environment. The
only source in this vault that describes the system as an operator meets it rather
than as an architect designed it.

## What it records that no other document does

**The document division of labour.** [[engineering-constitution]] holds the
principles and is read before structural changes; [[plan]] holds architecture and
research; [[roadmap]] holds delivery order. Three documents, three jobs, no overlap.

**The real database story.** Development runs against a local `pgvector/pgvector:pg16`
container on port 5434, matching production. Hosted Postgres is **Neon**, used
when something outside the laptop needs the data. Migrations must use Neon's
**direct** endpoint, not the pooler, because Alembic runs DDL in a transaction and
a pooled connection in transaction mode cannot hold one reliably. Application
traffic can use the pooled endpoint. This is the concrete detail [[plan]] §3.2
does not have, having specified Aurora — see [[database-choice]].

**The model platform switch as it actually exists.** `GENESIS_MODEL_PLATFORM`
selects between `anthropic_api` (the default; no cloud account in the path,
prepaid credits with a console spend limit), `claude_platform_aws`, and
`bedrock_mantle`. The request body is identical across all three, **asserted by a
test**, so switching is configuration. Note the divergence from [[plan]] §1, which
names Claude Platform on AWS as the default — see [[model-platform]].

**The check commands**, which are the [[pre-ship-checklist]] in executable form:

```sh
uv run ruff check api/ ; uv run mypy api/genesis_api ; uv run pytest api/tests -q
cd api && uv run alembic heads          # must print exactly one line
uv run alembic revision --autogenerate  # diff must be empty
```

## What it is silent on

Everything about the product. No mention of the stylist, the catalog, the trend
studio, or any milestone. It is a setup document and stays one.
