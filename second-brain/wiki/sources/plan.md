---
title: PLAN.md — architecture and research
type: source-summary
sources: [PLAN.md]
related: ["[[roadmap]]", "[[engineering-constitution]]", "[[readme]]", "[[model-platform]]", "[[two-planes-one-monorepo]]", "[[unit-economics]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

The founding research and architecture document, prepared 2026-09-03 against an
empty working directory, and written to be approved, rejected or re-scoped rather
than to describe a system that exists (PLAN.md §0). ~70KB across fourteen
sections. It is the answer to "what should we build and why", not "what is built"
— for that, see [[roadmap]] §2.

## What it decides

Ten decisions carry the document (PLAN.md §1), and every one of them is still the
operative answer:

- Agents run on **Bedrock AgentCore** with the **Strands** SDK — see [[agent-runtime]].
- Claude is reached through **Claude Platform on AWS** by default, with Bedrock
  Mantle as a per-tenant switch — see [[model-platform]].
- **Opus 5** for agent turns, **Haiku 4.5** for extraction, **Sonnet 5** only on
  eval parity — see [[model-tiering]].
- Images from the **Stability suite**, explicitly not Nova Canvas — see [[image-generation]].
- The catalog is **layered across sanctioned sources**, no scraping — see [[catalog-sources]].
- Trend data is **licensed, platform-API and owned**, never a social firehose —
  see [[trend-corpus]].
- **Aurora Postgres + pgvector** with **FashionSigLIP** embeddings — see
  [[embeddings-and-vectors]] and [[database-choice]].
- **Two planes in one monorepo**, TypeScript product and Python intelligence —
  see [[two-planes-one-monorepo]].
- Security mapped to the **OWASP LLM and Agentic Top 10 (2026)** — see
  [[tool-results-are-data]] and [[tenant-isolation]].
- Compliance designed in from day one, not retrofitted — see [[image-provenance]].

## Section map

| § | Subject | Wiki pages built from it |
|---|---|---|
| 0–1 | Context, the ten decisions | this page, all of `decisions/` |
| 2 | Product definition, competitive landscape | [[styling-intelligence]], [[enterprise-studio]] |
| 3 | System architecture, stack, service boundaries, data model | [[two-planes-one-monorepo]], [[database-is-the-api]], [[atomic-facts-not-derivations]] |
| 4 | The AI layer — model paths, tiering, agents, retrieval, imagery, trend, efficiency, evals | [[model-platform]], [[model-tiering]], [[agent-runtime]], [[hybrid-catalog-search]], [[prompt-caching]], [[evals-as-gates]], [[trend-corpus]] |
| 5 | Product data sources | [[catalog-sources]] |
| 6 | Security architecture | [[tool-results-are-data]], [[tenant-isolation]] |
| 7 | Privacy, legal, compliance | [[image-provenance]] |
| 8 | Infrastructure and operations | [[database-choice]] |
| 9 | Cost model | [[unit-economics]] |
| 10 | Two-track roadmap by week | superseded in practice by [[roadmap]] |
| 11 | Repository layout, Phase 0 steps | [[two-planes-one-monorepo]] |
| 12 | Verification plan | [[evals-as-gates]], [[pre-ship-checklist]] |
| 13 | Open decisions | [[open-decisions]] |
| 14 | Key sources | — |

## What it is silent on

- **Anything that has happened since 2026-09-03.** It assumes an empty directory.
  Its week-by-week calendar in §10 has been superseded by [[roadmap]], which was
  written two days later against a repository that already had a working core.
- **The actual database in use.** §3.2 specifies Aurora Serverless v2; the project
  currently runs local Postgres and hosted Neon ([[readme]]). See [[database-choice]].
- **Staffing reality.** §10 is written for three engineers plus design. [[roadmap]]
  §6 states the real number: one engineer with an AI pair.

## Where it marks its own uncertainty

The document tags unverified facts with `[verify]` and lists them in §13: Bedrock
batch support for Sonnet 5 and Opus 5, Stability per-image editing prices on
Bedrock, whether C2PA manifests survive the Bedrock path, Google Virtual Try-On
per-image price, and Affiliate.com terms. These markers survive into the wiki
rather than being laundered into stated facts.
