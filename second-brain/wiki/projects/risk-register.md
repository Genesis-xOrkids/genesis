---
title: Risk register
type: project
sources: [ROADMAP.md]
related: ["[[catalog-supply]]", "[[commerce-and-compliance]]", "[[evals-as-gates]]", "[[unit-economics]]", "[[no-silent-fallbacks]]", "[[enterprise-studio]]", "[[current-state]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

Eight risks with impact, likelihood and mitigation (ROADMAP.md §7). Read for the
mitigations rather than the ratings — most name a mechanism that already exists.

| # | Risk | Impact / likelihood | Mitigation |
|---|---|---|---|
| R1 | Catalog coverage too thin for credible outfits | High / Medium | Measure breadth at C1 before building on it. Sanctioned-protocol adoption looked universal on sampled storefronts — encouraging, but a small sample |
| R2 | Affiliate applications rejected for lack of traffic | High / Medium | File early; lead with platform-native and aggregator routes that don't gate on volume |
| R3 | Stylist quality plateaus below the rubric target | High / Medium | Evaluation first, so the plateau is visible early. **Retrieval quality is the usual culprit before prompting is** |
| R4 | Model spend exceeds the unit economics | Medium / Medium | Per-call cost attribution already exists. Enforce per-session budgets and cache aggressively before considering a cheaper model |
| R5 | A storefront changes shape and ingestion degrades quietly | Medium / **High** | Quarantine already makes this visible as a number. **Alert on the rate, not just record it** |
| R6 | Legal exposure from undisclosed commercial links or unlabelled AI content | High / Low | X3 is on the critical path to public launch, not after it |
| R7 | Solo-developer concentration risk | High / Medium | Everything committed, reviewed by CI, documented. The principles file exists so a second engineer is productive without archaeology |
| R8 | Enterprise track never starts because consumer work expands | Medium / **High** | The trigger in §5.5 is written down precisely so this decision is deliberate |

## The two rated high-likelihood

**R5 and R8**, and they fail in opposite ways. R5 is a technical failure that
hides itself — the pipeline reports success while writing garbage — and its
mitigation is a monitoring change on a mechanism that already exists
([[no-silent-fallbacks]]). R8 is an organisational failure that is entirely
visible while it happens and has no mechanism at all, only a written trigger
([[enterprise-studio]]).

## R3 is the one worth internalising

"Retrieval quality is the usual culprit before prompting is." This was borne out
before the stylist agent was even built: C3's category precision sat at 20% on
semantic queries, and the fix was in labelling and retrieval, not in any prompt
(commit `367058a`, "the labels were wrong, not the retrieval"). See
[[hybrid-catalog-search]].

## R7 and this vault

The mitigation for solo-developer concentration is that everything is written
down. This second brain is downstream of that: the risk is not that the code is
lost, it is that the *reasoning* is, and the reasoning lives in three documents
totalling ~115KB. See [[engineering-constitution]].
