---
title: Where Claude runs — three paths, one gateway
type: decision
sources: [PLAN.md, README.md]
related: ["[[provider-agnostic-intelligence]]", "[[model-tiering]]", "[[prompt-caching]]", "[[tenant-isolation]]", "[[plan]]", "[[readme]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## The decision

Abstract the model client behind one `ModelGateway` and pick the platform per
tenant. Three paths exist, the request body is identical on all three, and
switching is configuration (PLAN.md §1 decision 2, §4.1).

## What each path gives up

| | Claude Platform on AWS | Bedrock Mantle | Bedrock legacy |
|---|---|---|---|
| Data processor | Anthropic (`inference_geo:"us"` pins to US at 1.1×) | AWS, zero operator access | AWS |
| Model IDs | bare: `claude-opus-5` | `anthropic.`-prefixed | geo-prefixed `us.`/`eu.` |
| Structured outputs | Yes | **No** (Sonnet 5) | Haiku 4.5 yes, Sonnet 5 no |
| Batch API (50% off) | Yes | **No** | "select models" `[verify]` |
| Server tools (web search, fetch, code exec) | Yes | **No** | No |
| Files API, Skills, MCP connector, beta headers | Yes | **No** | No |
| Guardrails | via standalone `ApplyGuardrail` | not integrated → `ApplyGuardrail` | Integrated |
| Compliance | PrivateLink; no HIPAA program; ZDR on request | FedRAMP High / HIPAA path | same |
| Billing | AWS Marketplace, Claude Consumption Units | AWS bill, third-party line item | same |

## Why Platform on AWS is the plan's default

Its extras map one-to-one onto what this product needs (PLAN.md §4.1):
**structured outputs** for `StyleProfile` and attribute JSON, the **Batch API** for
nightly catalog and trend enrichment at half price ([[unit-economics]]), and **web
fetch** for reading brand pages on request.

Bedrock Mantle is offered as a **per-tenant setting** for enterprise customers
whose security review demands AWS as sole data processor. Because the request
shape is identical, that is configuration plus a small feature-fallback table:
tool-use JSON validated with Pydantic instead of structured outputs. Everything
else on the AWS side — AgentCore, Guardrails, Stability, embeddings, S3 Vectors —
is model-agnostic and unchanged.

## Divergence between plan and practice

PLAN.md §1 names Claude Platform on AWS the default. **README.md names
`anthropic_api` the default**, described as "no cloud account in the path; prepaid
credits with a console spend limit."

Both documents are current and they disagree. The reconciliation is that the
gateway was built with a fourth, first-party driver (commit `b51da0e`, "Add
first-party Anthropic driver and prepare for a hosted database"), and the
first-party path is the pragmatic default for a solo developer with no AWS account
in the loop. The plan's default remains correct for the architecture it describes;
nothing has decided against it. Recorded here rather than resolved.

## What makes the abstraction real

**The request body is identical on all three, asserted by a test** (README.md).
Without that assertion the gateway is a claim; with it, the platform is a
configuration value. See [[provider-agnostic-intelligence]].
