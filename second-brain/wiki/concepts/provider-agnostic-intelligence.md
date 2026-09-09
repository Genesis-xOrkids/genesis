---
title: Provider-agnostic intelligence
type: concept
sources: [CLAUDE.md, PLAN.md, README.md]
related: ["[[model-platform]]", "[[model-tiering]]", "[[prompt-caching]]", "[[source-agnostic-core]]", "[[unit-economics]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

Model providers, image providers and agent memory sit behind adapters —
`ModelGateway`, `ImageProvider`, `MemoryStore` — and **core code never imports a
vendor SDK directly** (CLAUDE.md, Service design).

For models this is absolute: every model call goes through one `ModelGateway`,
which owns provider selection per tenant, prompt-cache breakpoints, usage and cost
logging, and guardrails. No direct SDK calls anywhere else (CLAUDE.md, Agents).

## What the gateway makes switchable

Three platforms behind one interface, differing only in the model id and the
client (README.md):

| `GENESIS_MODEL_PLATFORM` | Use |
|---|---|
| `anthropic_api` | Default today. No cloud account in the path; prepaid credits with a console spend limit. |
| `claude_platform_aws` | Full API parity, billed through AWS Marketplace. Bare model ids: `claude-opus-5`. |
| `bedrock_mantle` | AWS as sole data processor, for enterprise security reviews. `anthropic.`-prefixed ids. |

**The request body is identical on all three, asserted by a test.** That assertion
is what turns "we have an abstraction" into "switching is configuration" — without
it the adapter is a claim rather than a property. See [[model-platform]] for what
each platform actually gives up.

## Why it is worth the indirection

The K axis. CLAUDE.md requires designing for K model and image providers from day
one, and PLAN.md §6.2 lists a concrete reason: dual model paths give failover
across *separate capacity pools*, which a single-provider integration cannot. The
image side has the same shape — [[image-generation]] has to route between Stability
on Bedrock, FLUX off-AWS, and a try-on provider that is off-AWS entirely.

## What the gateway is responsible for

- **Cost.** Per-call cost from reported usage, attributed to tenant and session.
  The unit economics in [[unit-economics]] are only enforceable because this
  exists.
- **Cache breakpoints.** See [[prompt-caching]].
- **Guardrails.** `ApplyGuardrail` on input and output.
- **Structured output policy.** Structured outputs on Claude Platform on AWS; on
  Bedrock Mantle, tool-use JSON validated with Pydantic. A validation failure
  raises or retries — never coerced into a default ([[no-silent-fallbacks]]).

## Status

Built. ROADMAP.md App. A: "Three platforms, route-based model selection, per-call
cost from reported usage". `intelligence/model_gateway/gateway.py` and
`pricing.py`; tested in `intelligence/tests/test_model_gateway.py`.
