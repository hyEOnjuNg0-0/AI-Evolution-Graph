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

from aievograph.domain.models import Author, Paper, ScoredPaper
from aievograph.domain.ports.vector_repository import VectorRepositoryPort

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
    node = record["p"]
    raw_authors: list[Any] = record["authors"] or []
    authors = [
        Author(author_id=a["author_id"], name=a["name"])
        for a in raw_authors
        if a is not None and a.get("author_id") and a.get("name")
    ]
    publication_year = node.get("publication_year")
    if publication_year is None:
        raise ValueError(
            f"Paper node missing required field 'publication_year': paper_id={node.get('paper_id')}"
        )
    paper = Paper(
        paper_id=node["paper_id"],
        title=node["title"],
        publication_year=publication_year,
        venue=node.get("venue"),
        abstract=node.get("abstract"),
        citation_count=node.get("citation_count") or 0,
        reference_count=node.get("reference_count") or 0,
        authors=authors,
    )
    return ScoredPaper(paper=paper, score=float(record["score"]))


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
