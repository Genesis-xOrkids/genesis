---
title: Open decisions
type: decision
sources: [ROADMAP.md, PLAN.md]
related: ["[[roadmap]]", "[[plan]]", "[[enterprise-studio]]", "[[trend-corpus]]", "[[embeddings-and-vectors]]", "[[consumer-application]]", "[[database-choice]]", "[[catalog-supply]]"]
created: 2026-09-07
last-updated: 2026-09-29
---

## What it is

Six decisions with a stated deadline and a **default if unanswered** (ROADMAP.md
§8). The defaults are the useful part: none of these blocks work, because each has
a written fallback.

| # | Decision | Needed by | Default if unanswered |
|---|---|---|---|
| D1 | Hosting platform for the web application | A5 | The one whose free tier permits commercial use |
| D2 | Embedding inference: hosted API or self-managed | C3 | Hosted, revisit at volume |
| D3 | Product images copied to our own storage, or hot-linked | C2 | Hot-link for the demo, copy when links start rotting |
| D4 | Authentication provider | A4 | The one bundled with the database platform, unless enterprise SSO lands first |
| D5 | Data licensing budget for the trend corpus | Before E1 | **Enterprise track does not start** |
| D6 | Target customer segment sharp enough to pick the brand mix | C2 | Contemporary womenswear, as the plan assumes |

## The two that are not really deferrable

**D5** is the gate on half the business. Its default is not a fallback, it is a
"no" — [[enterprise-studio]] does not start. And the roadmap is specific that the
decision belongs **before E1, not during E3 where the money is spent**
([[trend-corpus]]).

**D6** determines the brand mix, and [[catalog-supply]] C2 is already stalled on
breadth. Every storefront added under the default assumption is a bet on
contemporary womenswear that gets more expensive to unwind as the catalog grows.

## Already answered in practice

**D2** — hosted, per C3's stated choice, with the 30× unit-cost gap documented on
[[embeddings-and-vectors]]. Revisit trigger: volume.

## Still open from PLAN.md §13

Separate from the roadmap's list, and older:

1. Team size and start date — determines whether the parallel calendar holds.
   Since answered in practice: one engineer with an AI pair (ROADMAP.md §6).
2. Launch geography: US with EU-ready design (assumed).
3. Data licensing budget — the same question as D5.
4. Whether to apply to the Shopify Agentic Storefront / UCP and Pinterest Trends
   partner programs immediately. **Recommended; lead times are weeks.** This is
   [[commerce-and-compliance]] X1 and it has not been filed.

## Catalog taxonomy gaps, 2026-09-28

Two groups of products are left without a category on purpose. Both were
measured in a sample of every registered storefront's feed ([[catalog-supply]]).

- **Hair accessories.** Scrunchies, headbands, claw clips, hair ties and hair
  bows: 96 products in the sample, from Hill House, Alo, Knix, Lunya and Pepper.
  They are worn, so they are not rejected, but `Category` has no value for
  them. Fashionpedia gives them a category of their own. For now they stay null,
  and a tag cannot give them a wrong category. **Open:** add `hair_accessory`,
  or keep them null?
- **Rothy's model-name titles.** "The Point II", "The Square" and "The Monty"
  name a model rather than a garment. 244 products in the sample have no
  product type, tags or description to fall back on. No vocabulary can place
  them without guessing, so they are left to C3's image route.

## The `[verify]` list

Facts the plan could not confirm from a primary source, which should be checked
before they drive a purchase or a contract (PLAN.md §0, §13):

- Bedrock batch support for Sonnet 5 / Opus 5.
- Stability editing-suite per-image prices on Bedrock.
- **Whether C2PA manifests survive the Bedrock path** — the one with a compliance
  consequence ([[image-provenance]]).
- Google Virtual Try-On per-image price.
- Affiliate.com terms and price.
