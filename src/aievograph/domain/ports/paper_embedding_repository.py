from abc import ABC, abstractmethod


class PaperEmbeddingRepositoryPort(ABC):
    """Domain port for fetching stored paper embedding vectors.

    Separate from VectorRepositoryPort (Layer B) because this port is
    concerned only with reading embeddings for a known set of paper_ids,
    not with index management or global similarity search.
    """

    @abstractmethod
    def get_embeddings(self, paper_ids: list[str]) -> dict[str, list[float]]:
        """Return stored embedding vectors for the given paper_ids.

        Paper nodes that have no embedding stored are omitted from the result;
        callers must handle the missing-key case.

        Args:
            paper_ids: IDs of papers whose embeddings are needed.

        Returns:
            dict mapping paper_id → embedding vector (same order as stored).
        """
        raise NotImplementedError
