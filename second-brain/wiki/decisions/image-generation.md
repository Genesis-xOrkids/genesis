---
title: Image generation and editing
type: decision
sources: [PLAN.md]
related: ["[[image-provenance]]", "[[enterprise-studio]]", "[[provider-agnostic-intelligence]]", "[[unit-economics]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## The decision

The **Stability AI suite on Bedrock** as the AWS-native path, **FLUX.2 / FLUX
Kontext** (via fal.ai or BFL) as the premium consistency engine for B2B, and
**FASHN or Google Virtual Try-On** for try-on (PLAN.md §1 decision 4, §4.5).

## The warning that leads the decision

> **Do not build on Amazon Nova Canvas — it reaches end of life 2026-09-30.**

Nova 2 Omni image generation is preview-only behind Nova Forge at $100K/year. The
obvious AWS-native default is a dead end, and it dies three weeks from now.

## Tool per job

| Need | Primary | Premium alternative |
|---|---|---|
| Text→garment concept | Stable Image Ultra / SD3.5 Large | FLUX.2 Pro, Imagen 4 Ultra |
| Sketch→render | Stability **Control Sketch / Control Structure** | FLUX Kontext |
| Colourway and detail iteration | **Search & Recolor**, **Search & Replace**, Inpaint/Outpaint, Erase Object | FLUX Kontext multi-turn |
| Consistency across a collection | Style Guide / Style Transfer, seed + reference conditioning | **FLUX Kontext** (reference-image identity), LoRA on brand assets (≈ tens of dollars to train) |
| Flat-lay cutouts | Remove Background | — |
| On-model try-on | — | FASHN v1.6 ($0.075, <$0.04 at volume), Google VTO, Kling Kolors |
| Print upscale | Conservative / Creative Upscale | — |

Cost anchors: Ultra ≈ $0.08/image, Core ≈ $0.03–0.04, SD3.5 Large ≈ $0.065–0.08,
all marked `[verify]` against the Bedrock pricing page.

## The pipeline

Brief → Opus 5 builds a prompt plan from brand codes and trend attributes → sketch
→ 4–8 candidate renders → **critic/IP scoring** → stylist review → iterations →
**C2PA signing** → store with lineage.

Every input and output image is moderated with Bedrock Guardrails image filters,
and uploads containing third-party logos are rejected when generating.

## Why it sits behind an adapter

Three providers across two clouds and one off-cloud vendor, one of which (Nova
Canvas) was the natural default and is being retired. `ImageProvider` is the K
axis made concrete — see [[provider-agnostic-intelligence]]. Try-on in particular
is off-AWS entirely and is explicitly isolated behind a `tryon` adapter.

## The non-negotiable output step

No image leaves without a C2PA manifest, an invisible watermark, a visible label,
and a `GenerationJob` lineage row. See [[image-provenance]], including the open
`[verify]` on whether Stability's manifests survive the Bedrock path.

## Status

Not built. `intelligence/imagery/` is an empty directory; deferred with
[[enterprise-studio]]. Lookbook imagery for the consumer side is not on the
current roadmap's critical path either.
