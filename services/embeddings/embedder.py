"""Fashion-tuned image and text embeddings.

Uses Marqo FashionSigLIP, a SigLIP model fine-tuned on a million fashion
products with their categories, colours, materials and details. General-purpose
image models do not separate a boat neck from a bateau or a barrel leg from a
wide one, and those distinctions are the entire job here.

**Images are the primary signal, and that is not an implementation detail.**
This is a contrastive model: it was trained to put an image and its description
at the same point in one shared space. Querying that space with text and
matching against image vectors is the objective it was trained on. Matching text
against text uses only half the model, on a task it was never optimised for, and
loses most of the fashion-specific gain. So products are embedded from their
photographs, and only fall back to their text when no image can be fetched.

The model runs locally. Hosted inference is the obvious later move and needs
only this class replaced, but it would require credentials for a service nobody
has chosen yet, and twenty thousand products is minutes of work on a laptop GPU.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:  # pragma: no cover - import cost is the reason for the guard
    import torch

log = structlog.get_logger(__name__)

MODEL_ID = "hf-hub:Marqo/marqo-fashionSigLIP"
# Matches products.embedding. A mismatch is a migration, not a config change,
# so the constant lives next to the model that determines it.
EMBEDDING_DIMS = 768


def product_document(
    *,
    title: str,
    brand: str | None = None,
    category: str | None = None,
    color: str | None = None,
    silhouette: str | None = None,
    pattern: str | None = None,
    description: str | None = None,
) -> str:
    """The text form of a product, for the fallback path.

    Deliberately terse and attribute-led rather than the marketing copy. The
    text tower was trained against short product descriptors, and feeding it two
    paragraphs of brand voice buries the three words that identify the garment.
    """
    parts = [part for part in (brand, title) if part]
    attributes = [a for a in (category, color, silhouette, pattern) if a]
    if attributes:
        parts.append(", ".join(attributes))
    if description:
        parts.append(description[:200])
    return ". ".join(parts)


class FashionEmbedder:
    """Embeds text queries and product images into one shared space.

    The model is loaded on first use rather than at construction, so importing
    this module stays cheap for the processes that never embed anything.
    """

    def __init__(self, *, device: str | None = None, batch_size: int = 64) -> None:
        self._device_preference = device
        self._batch_size = batch_size
        self._model: Any = None
        self._tokenizer: Any = None
        self._preprocess: Any = None
        self._device: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        import open_clip
        import torch

        if self._device_preference:
            device = torch.device(self._device_preference)
        elif torch.backends.mps.is_available():
            # Apple silicon. Roughly an order of magnitude faster than CPU here,
            # which is the difference between minutes and an afternoon.
            device = torch.device("mps")
        elif torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")

        model, _, preprocess = open_clip.create_model_and_transforms(MODEL_ID)
        model = model.to(device).eval()

        self._model = model
        self._preprocess = preprocess
        self._tokenizer = open_clip.get_tokenizer(MODEL_ID)
        self._device = device
        log.info("embedder_loaded", model=MODEL_ID, device=str(device))

    @property
    def device(self) -> str:
        self._load()
        return str(self._device)

    def _normalize(self, features: torch.Tensor) -> list[list[float]]:
        """Unit-normalize so cosine distance and dot product agree.

        pgvector's cosine operator normalizes internally, but storing unit
        vectors keeps the stored numbers comparable to anything computed outside
        the database, and makes a wrong-magnitude bug visible rather than absorbed.
        """
        features = features / features.norm(dim=-1, keepdim=True)
        return [row.tolist() for row in features.detach().cpu()]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text. Used for queries, and for products with no image."""
        if not texts:
            return []
        self._load()
        import torch

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            chunk = texts[start : start + self._batch_size]
            tokens = self._tokenizer(chunk).to(self._device)
            with torch.no_grad():
                vectors.extend(self._normalize(self._model.encode_text(tokens)))
        return vectors

    def embed_text(self, text: str) -> list[float]:
        """Satisfies the Embedder protocol that catalog search expects."""
        return self.embed_texts([text])[0]

    def embed_images(self, images: list[bytes]) -> list[list[float] | None]:
        """Embed a batch of image bytes.

        Returns None in place of any image that cannot be decoded rather than
        failing the batch. A corrupt or truncated download is a fact about one
        product, and dropping the other thirty-one because of it would make a
        backfill of twenty thousand products impossible to finish.
        """
        if not images:
            return []
        self._load()
        import torch
        from PIL import Image, UnidentifiedImageError

        results: list[list[float] | None] = [None] * len(images)
        decoded: list[Any] = []
        positions: list[int] = []
        for index, raw in enumerate(images):
            try:
                image = Image.open(io.BytesIO(raw)).convert("RGB")
            except (UnidentifiedImageError, OSError, ValueError):
                continue
            decoded.append(self._preprocess(image))
            positions.append(index)

        for start in range(0, len(decoded), self._batch_size):
            chunk = decoded[start : start + self._batch_size]
            batch = torch.stack(chunk).to(self._device)
            with torch.no_grad():
                vectors = self._normalize(self._model.encode_image(batch))
            for offset, vector in enumerate(vectors):
                results[positions[start + offset]] = vector
        return results
