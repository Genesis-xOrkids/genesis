---
title: Every generated image carries provenance
type: concept
sources: [CLAUDE.md, PLAN.md, ROADMAP.md]
related: ["[[image-generation]]", "[[null-means-unknown]]", "[[enterprise-studio]]", "[[commerce-and-compliance]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

Four things attach to every generated image, and **an image without lineage does
not leave the system** (CLAUDE.md, Agents):

1. A **C2PA manifest**.
2. An **invisible watermark**.
3. A **visible label**.
4. A **`GenerationJob` lineage row** recording inputs, prompt hash, and human edits.

## Why it is a data-model decision, not a rendering one

EU AI Act Article 50 came into force 2026-08-02, requires machine-readable marking
*and* visible labelling of AI-generated images, and carries fines to €15M or 3%
(PLAN.md §7). Retrofitting provenance is not possible: the manifest has to be
signed at generation time and the lineage row has to exist before the image is
stored. So it is designed in from day one rather than added before launch, and
adopted globally rather than gated by geography.

The UI side follows [[null-means-unknown]]: an image is treated as AI-generated
**unless** provenance says `human_made === true`. The label is the safe default.

## The second job the lineage row does

Copyright. US Copyright Office Part 2 (Jan 2025) and *Thaler v. Perlmutter*
establish that purely AI-generated works are not protectable, but meaningful human
contribution can be. So the studio records prompts, selections, edits and stylist
authorship per concept, and exports an **authorship record** with each design, so
brands can claim protection for the human-authored elements (PLAN.md §7).

The same rows serve compliance, IP claims, and audit. That is why `GenerationJob`
carries inputs, prompt hash, cost and watermark id, and `Concept` carries
`human_edits[]` and `c2pa_manifest_ref` (PLAN.md §3.4).

## Open verification

PLAN.md flags `[verify]`: Stability's API embeds C2PA manifests and an invisible
watermark, but **whether manifests survive the Bedrock path is unconfirmed**. The
design response is to add an independent C2PA signing step (c2pa-node / c2pa-rs)
rather than depend on the provider's, so provenance does not rest on an
unverified claim.

## The adjacent disclosure rules

Not the same thing, often confused with it (ROADMAP.md §5.4 X3):

- **FTC material-connection disclosure** before the *first* outbound click, on
  every surface carrying a commercial link — verified by test, not inspection.
- **Chatbot disclosure**: "you are chatting with an AI stylist".

## Status

Not built. The imagery plane is a directory (`intelligence/imagery/`) with no
implementation; image generation is deferred with [[enterprise-studio]].
