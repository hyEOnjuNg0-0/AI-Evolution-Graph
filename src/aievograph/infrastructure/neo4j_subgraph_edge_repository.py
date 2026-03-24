"""
neo4j.Driver
        ↓
Neo4jSubgraphEdgeRepository  (implements SubgraphEdgeRepositoryPort)
        ↓
  get_citation_edges(paper_ids)
      → list[tuple[str, str]]  (citing_paper_id, cited_paper_id)

Returns only edges where both endpoints are in paper_ids,
so the caller receives a self-contained subgraph edge set.
"""

import logging

from neo4j import Driver

from aievograph.domain.ports.subgraph_edge_repository import SubgraphEdgeRepositoryPort

logger = logging.getLogger(__name__)

_GET_EDGES = """
MATCH (a:Paper)-[:CITES]->(b:Paper)
WHERE a.paper_id IN $paper_ids AND b.paper_id IN $paper_ids
RETURN a.paper_id AS citing, b.paper_id AS cited
"""


class Neo4jSubgraphEdgeRepository(SubgraphEdgeRepositoryPort):
    """Fetch intra-subgraph citation edges from Neo4j."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def get_citation_edges(
        self, paper_ids: list[str]
    ) -> list[tuple[str, str]]:
        """Return citation edges within the given paper set.

        Args:
            paper_ids: IDs of papers that form the subgraph.

        Returns:
            List of (citing_paper_id, cited_paper_id) tuples.
        """
        if not paper_ids:
            return []

        with self._driver.session() as session:
            result = session.run(_GET_EDGES, paper_ids=paper_ids)
            edges = [
                (record["citing"], record["cited"])
                for record in result
                if record["citing"] is not None and record["cited"] is not None
            ]

        logger.debug(
            "Fetched %d citation edges within subgraph of %d papers.",
            len(edges),
            len(paper_ids),
        )
        return edges
