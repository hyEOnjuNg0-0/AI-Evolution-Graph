"""
OpenAIEmbeddingClient  (implements EmbeddingPort)
    ↓
  embed()       → single text  → list[float]  (dim=1536)
  embed_batch() → list[text]   → list[list[float]]
"""

import logging

from openai import OpenAI

from aievograph.domain.ports.embedding_port import EmbeddingPort

logger = logging.getLogger(__name__)

# text-embedding-3-small produces 1536-dimensional vectors
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


class OpenAIEmbeddingClient(EmbeddingPort):
    """Infrastructure adapter that calls the OpenAI Embeddings API."""

    def __init__(self, api_key: str) -> None:
        self._client = OpenAI(api_key=api_key)

    def embed(self, text: str) -> list[float]:
        """Return a 1536-dim embedding for a single text."""
        response = self._client.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL,
        )
        logger.debug("Generated embedding for text of length %d.", len(text))
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for each text in the list (preserves order)."""
        if not texts:
            return []
        response = self._client.embeddings.create(
            input=texts,
            model=EMBEDDING_MODEL,
        )
        logger.debug("Generated batch embeddings for %d texts.", len(texts))
        # OpenAI returns items in the same order as the input
        return [item.embedding for item in response.data]
