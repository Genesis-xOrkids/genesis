---
title: No silent fallbacks — quarantine instead
type: concept
sources: [CLAUDE.md, ROADMAP.md]
related: ["[[null-means-unknown]]", "[[one-write-door]]", "[[source-agnostic-core]]", "[[provider-agnostic-intelligence]]", "[[risk-register]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

Missing or malformed input raises (Python) or throws (TypeScript). A record that
fails validation is **quarantined with its error**, not defaulted. Named
prohibitions (CLAUDE.md, Code):

> Never default a price to 0, a currency to USD, a size to "M", or a model output
> to an empty object.

The same rule applies to model calls: a structured-output validation failure
raises or retries, and a bad model output is never coerced into a default
(CLAUDE.md, Agents).

## Quarantine as a first-class table

The alternative to defaulting is not dropping — it is storing the failure. The
schema has a dedicated quarantine table (migration `29d57d09d77d`, "quarantine
table for records that fail…"), and pipelines are required to be idempotent and
resumable, with a failing record quarantined *without failing the batch*
(CLAUDE.md, Agents).

This is what makes per-run reporting meaningful: [[catalog-supply]] C1 reports
products written, offers written, and **quarantined by stage**, with acceptance at
under 5% quarantined and every quarantined record's reason attributable to a named
cause (ROADMAP.md §5.1).

## Why it is a monitoring property, not just a coding one

Risk R5 in ROADMAP.md §7 is "a storefront changes shape and ingestion degrades
quietly" — rated the *highest-likelihood* risk in the register. Its mitigation is
exactly this mechanism plus one addition:

> Quarantine already makes this visible as a number. **Alert on the rate, not just
> record it.**

A default would have made that degradation invisible: the pipeline would report
success while writing zero-priced products in the wrong currency. Quarantine turns
a silent corruption into a visible number, and the alert turns the visible number
into something someone sees.

## The verbose-logging counterpart

For outbound writes the rule extends further (CLAUDE.md, Operations): every request
to a model provider, image provider, commerce protocol, affiliate network or OAuth
token exchange logs the full request and response with secrets redacted, and
response bodies are stored alongside send history — because **a 200 means
"received", not "processed"**. Feed accepted is not feed indexed; checkout
initiated is not checkout confirmed.
