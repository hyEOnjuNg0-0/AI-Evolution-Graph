"""
Neo4jVectorRepository  (implements VectorRepositoryPort)
    ↓
  create_vector_index() → VECTOR INDEX on (:Paper).embedding
  store_embedding()     → SET p.embedding = $embedding
  similarity_search()   → db.index.vector.queryNodes → list[ScoredPaper]
"""

import logging
from typing import Any

from neo4j import Driver

from aievograph.domain.models import ScoredPaper
from aievograph.domain.ports.vector_repository import VectorRepositoryPort
from aievograph.infrastructure.neo4j_graph_repository import _record_to_paper

logger = logging.getLogger(__name__)

VECTOR_INDEX_NAME = "paper_embedding_idx"
EMBEDDING_DIMENSIONS = 1536

_CREATE_VECTOR_INDEX = f"""
CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS
FOR (p:Paper) ON (p.embedding)
OPTIONS {{indexConfig: {{
    `vector.dimensions`: {EMBEDDING_DIMENSIONS},
    `vector.similarity_function`: 'cosine'
}}}}
"""

_STORE_EMBEDDING = """
MATCH (p:Paper {paper_id: $paper_id})
SET p.embedding = $embedding
"""

_SIMILARITY_SEARCH = f"""
CALL db.index.vector.queryNodes('{VECTOR_INDEX_NAME}', $top_k, $query_embedding)
YIELD node AS p, score
OPTIONAL MATCH (p)-[:WRITTEN_BY]->(a:Author)
RETURN p, collect(a) AS authors, score
ORDER BY score DESC
"""


def _record_to_scored_paper(record: Any) -> ScoredPaper:
    """Convert a Neo4j similarity-search record to a ScoredPaper domain object."""
    return ScoredPaper(paper=_record_to_paper(record), score=float(record["score"]))


class Neo4jVectorRepository(VectorRepositoryPort):
    """Infrastructure adapter for Neo4j vector index operations."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def create_vector_index(self) -> None:
        """Ensure the paper embedding vector index exists (idempotent)."""
        with self._driver.session() as session:
            session.run(_CREATE_VECTOR_INDEX)
        logger.info("Vector index '%s' created (or already exists).", VECTOR_INDEX_NAME)

    def store_embedding(self, paper_id: str, embedding: list[float]) -> None:
        """Set the embedding property on the Paper node with the given ID.

        Raises ValueError if no Paper with paper_id exists in the graph.
        """
        with self._driver.session() as session:
            result = session.run(_STORE_EMBEDDING, paper_id=paper_id, embedding=embedding)
            summary = result.consume()
        if summary.counters.properties_set == 0:
            raise ValueError(f"Paper not found in graph, cannot store embedding: {paper_id}")
        logger.debug("Stored embedding for paper: %s", paper_id)

    def similarity_search(
        self, query_embedding: list[float], top_k: int
    ) -> list[ScoredPaper]:
        """Return top-k papers by cosine similarity using the Neo4j vector index."""
        with self._driver.session() as session:
            result = session.run(
                _SIMILARITY_SEARCH,
                top_k=top_k,
                query_embedding=query_embedding,
            )
            return [_record_to_scored_paper(record) for record in result]
