"""Fashion-tuned embeddings.

Kept behind the ``Embedder`` protocol that catalog search is already written
against, so the model can move to hosted inference without search knowing.
"""

from services.embeddings.embedder import (
    EMBEDDING_DIMS,
    MODEL_ID,
    FashionEmbedder,
    product_document,
)

__all__ = ["EMBEDDING_DIMS", "MODEL_ID", "FashionEmbedder", "product_document"]
