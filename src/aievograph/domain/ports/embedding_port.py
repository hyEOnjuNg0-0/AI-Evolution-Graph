from abc import ABC, abstractmethod


class EmbeddingPort(ABC):
    """Domain port for generating text embedding vectors."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return an embedding vector for a single text."""
        raise NotImplementedError

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a list of texts (same order)."""
        raise NotImplementedError
