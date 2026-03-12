"""
Neo4j driver
        ↓
Neo4jGraphRepository  (implements GraphRepositoryPort)
        ↓
  upsert_paper   → (:Paper)-[:WRITTEN_BY]->(:Author)
  upsert_method  → (:Method)
  create_citation→ (:Paper)-[:CITES]->(:Paper)
  get_papers_by_year_range → list[Paper]
"""

import logging
from typing import Any

from neo4j import Driver

from aievograph.domain.models import Author, Citation, Method, Paper
from aievograph.domain.ports.graph_repository import GraphRepositoryPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_CREATE_INDEXES = [
    "CREATE INDEX paper_id_idx IF NOT EXISTS FOR (p:Paper) ON (p.paper_id)",
    "CREATE INDEX paper_year_idx IF NOT EXISTS FOR (p:Paper) ON (p.publication_year)",
    "CREATE INDEX author_id_idx IF NOT EXISTS FOR (a:Author) ON (a.author_id)",
    "CREATE INDEX method_name_idx IF NOT EXISTS FOR (m:Method) ON (m.name)",
]

_UPSERT_PAPER = """
MERGE (p:Paper {paper_id: $paper_id})
SET p.title            = $title,
    p.publication_year = $publication_year,
    p.venue            = $venue,
    p.abstract         = $abstract,
    p.citation_count   = $citation_count,
    p.reference_count  = $reference_count
WITH p
UNWIND $authors AS author_data
MERGE (a:Author {author_id: author_data.author_id})
SET a.name = author_data.name
MERGE (p)-[:WRITTEN_BY]->(a)
"""

_UPSERT_METHOD = """
MERGE (m:Method {name: $name})
SET m.method_type  = $method_type,
    m.description  = $description
"""

# Uses MATCH so that edges are only created between already-collected papers.
# If either paper is absent the query produces no rows and no edge is created.
_CREATE_CITATION = """
MATCH (citing:Paper {paper_id: $citing_paper_id})
MATCH (cited:Paper  {paper_id: $cited_paper_id})
MERGE (citing)-[:CITES {created_year: $created_year}]->(cited)
"""

_GET_PAPERS_BY_YEAR_RANGE = """
MATCH (p:Paper)
WHERE p.publication_year >= $start_year AND p.publication_year <= $end_year
OPTIONAL MATCH (p)-[:WRITTEN_BY]->(a:Author)
RETURN p, collect(a) AS authors
ORDER BY p.publication_year
"""


def _record_to_paper(record: Any) -> Paper:
    """Convert a Neo4j record from _GET_PAPERS_BY_YEAR_RANGE to a Paper domain object."""
    node = record["p"]
    raw_authors: list[Any] = record["authors"] or []
    authors = [
        Author(author_id=a["author_id"], name=a["name"])
        for a in raw_authors
        if a is not None and a.get("author_id") and a.get("name")
    ]
    return Paper(
        paper_id=node["paper_id"],
        title=node["title"],
        publication_year=node["publication_year"],
        venue=node.get("venue"),
        abstract=node.get("abstract"),
        citation_count=node.get("citation_count") or 0,
        reference_count=node.get("reference_count") or 0,
        authors=authors,
    )


class Neo4jGraphRepository(GraphRepositoryPort):
    """Infrastructure adapter that persists the citation graph in Neo4j."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    # ------------------------------------------------------------------
    # GraphRepositoryPort implementation
    # ------------------------------------------------------------------

    def create_indexes(self) -> None:
        """Ensure all required indexes exist (idempotent)."""
        with self._driver.session() as session:
            for cypher in _CREATE_INDEXES:
                session.run(cypher)
        logger.info("Neo4j indexes created (or already exist).")

    def upsert_paper(self, paper: Paper) -> None:
        author_data = [
            {"author_id": a.author_id, "name": a.name} for a in paper.authors
        ]
        with self._driver.session() as session:
            session.run(
                _UPSERT_PAPER,
                paper_id=paper.paper_id,
                title=paper.title,
                publication_year=paper.publication_year,
                venue=paper.venue,
                abstract=paper.abstract,
                citation_count=paper.citation_count,
                reference_count=paper.reference_count,
                authors=author_data,
            )
        logger.debug("Upserted paper: %s", paper.paper_id)

    def upsert_method(self, method: Method) -> None:
        with self._driver.session() as session:
            session.run(
                _UPSERT_METHOD,
                name=method.name,
                method_type=method.method_type,
                description=method.description,
            )
        logger.debug("Upserted method: %s", method.name)

    def create_citation(self, citation: Citation) -> None:
        with self._driver.session() as session:
            session.run(
                _CREATE_CITATION,
                citing_paper_id=citation.citing_paper_id,
                cited_paper_id=citation.cited_paper_id,
                created_year=citation.created_year,
            )
        logger.debug(
            "Created citation: %s -> %s",
            citation.citing_paper_id,
            citation.cited_paper_id,
        )

    def get_papers_by_year_range(self, start_year: int, end_year: int) -> list[Paper]:
        with self._driver.session() as session:
            result = session.run(
                _GET_PAPERS_BY_YEAR_RANGE,
                start_year=start_year,
                end_year=end_year,
            )
            return [_record_to_paper(record) for record in result]
