from abc import ABC, abstractmethod

from aievograph.domain.models import ScoredPaper


class VectorRepositoryPort(ABC):
    """Domain port for vector index operations on Paper nodes."""

    @abstractmethod
    def create_vector_index(self) -> None:
        """Create the vector index for paper embeddings (idempotent)."""
        raise NotImplementedError

    @abstractmethod
    def store_embedding(self, paper_id: str, embedding: list[float]) -> None:
        """Persist an embedding vector on the given Paper node."""
        raise NotImplementedError

    @abstractmethod
    def similarity_search(
        self, query_embedding: list[float], top_k: int
    ) -> list[ScoredPaper]:
        """Return top-k papers ranked by cosine similarity to query_embedding."""
        raise NotImplementedError
