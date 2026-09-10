---
title: Embeddings and vector storage
type: decision
sources: [PLAN.md, ROADMAP.md]
related: ["[[hybrid-catalog-search]]", "[[database-choice]]", "[[catalog-supply]]", "[[unit-economics]]", "[[fashion-taxonomy]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## The decision

**Marqo FashionSigLIP 2** (open weights, self-hosted) for fashion-tuned image and
text embeddings, with **Amazon Nova 2 Multimodal Embeddings** as the managed
fallback. Vectors live in **pgvector** alongside the relational data for the hot
catalog; **S3 Vectors** holds large cold corpora — trend image archives, brand
archives (PLAN.md §1 decision 7, §3.2).

## Why fashion-tuned rather than general CLIP

Measured: **+57% (v1) / +78% (v2) MRR over prior fashion CLIP** (PLAN.md §3.2).
General-purpose embeddings do not distinguish a drop-shoulder from a raglan, which
is exactly the distinction the product sells.

## Why one database instead of a vector store

At MVP scale, one database gives relational data, vectors and row-level tenant
security in the same place, with no synchronization problem between a product row
and its embedding. The stated migration trigger is specific: move hot catalog
search to OpenSearch **only when QPS demands sub-10ms**. See [[database-choice]].

S3 Vectors (GA Dec 2025) handles the cold side: up to 2B vectors per index,
$0.06/GB-month storage, ~100ms warm queries, **zero idle cost** — which is the
property that matters for an archive queried occasionally.

## The 30× cost gap

| Path | 1M images |
|---|---|
| FashionSigLIP self-hosted (~$1.5/h GPU at ~200 img/s) | ≈ **$3** compute |
| Nova 2 Multimodal Embeddings, managed | ≈ **$100** |

ROADMAP.md §5.1 C3 nonetheless chose **hosted inference initially rather than
self-managed GPU**, to revisit when volume justifies it — trading a 30× unit cost
for not operating a GPU endpoint while the catalog is 21K products. At 1M images
the arithmetic reverses. This is open decision D2.

## Rerank

Cohere Rerank 3.5 or Amazon Rerank on Bedrock, over the top-100 hybrid results,
before the agent sees anything ([[hybrid-catalog-search]]).

## Status

Built and measured. `services/embeddings/embedder.py` behind an interface search
was already written against, with `intelligence/pipelines/backfill_embeddings.py`
for the backfill. Vector and full-text search indexes are migration `a0f8614e62ba`.
Category precision on semantic queries: 20% → 79%.
