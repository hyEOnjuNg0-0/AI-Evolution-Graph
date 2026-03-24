"""
neo4j.Driver
        ↓
Neo4jPaperEmbeddingRepository  (implements PaperEmbeddingRepositoryPort)
        ↓
  get_embeddings(paper_ids)
      → dict[str, list[float]]  (paper_id → embedding vector)

Queries only Paper nodes that already have an embedding property stored,
so papers ingested before the embedding pipeline ran are silently omitted
and callers receive an empty slot for those IDs.
"""

import logging

from neo4j import Driver

from aievograph.domain.ports.paper_embedding_repository import PaperEmbeddingRepositoryPort

logger = logging.getLogger(__name__)

_GET_EMBEDDINGS = """
MATCH (p:Paper)
WHERE p.paper_id IN $paper_ids AND p.embedding IS NOT NULL
RETURN p.paper_id AS paper_id, p.embedding AS embedding
"""


class Neo4jPaperEmbeddingRepository(PaperEmbeddingRepositoryPort):
    """Fetch stored paper embedding vectors from Neo4j Paper nodes."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def get_embeddings(self, paper_ids: list[str]) -> dict[str, list[float]]:
        """Return stored embedding vectors for the requested paper_ids.

        Papers with no embedding property are omitted from the result dict.

        Args:
            paper_ids: IDs of papers whose embeddings are needed.

        Returns:
            dict mapping paper_id → embedding vector for papers that have one.
        """
        if not paper_ids:
            return {}

        with self._driver.session() as session:
            result = session.run(_GET_EMBEDDINGS, paper_ids=paper_ids)
            embeddings = {
                record["paper_id"]: list(record["embedding"])
                for record in result
                if record["paper_id"] is not None
            }

        logger.debug(
            "Fetched embeddings: %d / %d papers had embeddings stored.",
            len(embeddings),
            len(paper_ids),
        )
        return embeddings
