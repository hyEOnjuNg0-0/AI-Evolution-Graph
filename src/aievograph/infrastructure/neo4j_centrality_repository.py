"""
neo4j.Driver
        ↓
Neo4jCentralityRepository  (implements CentralityRepositoryPort)
        ↓
  compute_pagerank(paper_ids)   → dict[paper_id, float]  via GDS PageRank
  compute_betweenness(paper_ids)→ dict[paper_id, float]  via GDS Betweenness

GDS projection lifecycle per call:
  1. CALL gds.graph.project() [Cypher aggregation, GDS 2.1+] → named in-memory graph
  2. CALL gds.<algorithm>.stream($graph_name) → scores
  3. CALL gds.graph.drop($graph_name) → cleanup

Projection name is UUID-prefixed to prevent conflicts under concurrent calls.
"""

import logging
import uuid

from neo4j import Driver

from aievograph.domain.ports.centrality_repository import CentralityRepositoryPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

# Cypher aggregation projection (GDS 2.1+).
# OPTIONAL MATCH ensures isolated nodes (no CITES edges within the subgraph)
# are still included in the projection; gds.graph.project() handles null `m`.
_GRAPH_PROJECT = """
MATCH (n:Paper) WHERE n.paper_id IN $paper_ids
OPTIONAL MATCH (n)-[:CITES]->(m:Paper) WHERE m.paper_id IN $paper_ids
WITH gds.graph.project($graph_name, n, m,
     {relationshipType: 'CITES'}) AS g
RETURN g.graphName AS graphName, g.nodeCount AS nodeCount
"""

_PAGERANK_STREAM = """
CALL gds.pageRank.stream($graph_name, {maxIterations: 20, dampingFactor: 0.85})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).paper_id AS paper_id, score
"""

_BETWEENNESS_STREAM = """
CALL gds.betweenness.stream($graph_name)
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).paper_id AS paper_id, score
"""

_GRAPH_DROP = """
CALL gds.graph.drop($graph_name, false)
YIELD graphName
RETURN graphName
"""


class Neo4jCentralityRepository(CentralityRepositoryPort):
    """Compute subgraph-scoped centrality metrics using Neo4j GDS (2.1+)."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def compute_pagerank(self, paper_ids: list[str]) -> dict[str, float]:
        """Return GDS PageRank scores for the given paper subgraph."""
        if not paper_ids:
            return {}
        return self._run_algorithm(paper_ids, _PAGERANK_STREAM)

    def compute_betweenness(self, paper_ids: list[str]) -> dict[str, float]:
        """Return GDS Betweenness Centrality scores for the given paper subgraph."""
        if not paper_ids:
            return {}
        return self._run_algorithm(paper_ids, _BETWEENNESS_STREAM)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_algorithm(
        self, paper_ids: list[str], algorithm_query: str
    ) -> dict[str, float]:
        """Create a GDS projection, stream algorithm results, then drop the projection."""
        graph_name = f"centrality_{uuid.uuid4().hex}"
        with self._driver.session() as session:
            try:
                result = session.run(
                    _GRAPH_PROJECT, graph_name=graph_name, paper_ids=paper_ids
                )
                record = result.single()
                node_count = record["nodeCount"] if record else 0
                logger.debug(
                    "GDS projection '%s' created: %d nodes", graph_name, node_count
                )

                result = session.run(algorithm_query, graph_name=graph_name)
                scores: dict[str, float] = {
                    r["paper_id"]: r["score"]
                    for r in result
                    if r["paper_id"] is not None
                }
                return scores
            finally:
                # Always drop the projection to avoid leaking in-memory graphs.
                try:
                    session.run(_GRAPH_DROP, graph_name=graph_name)
                    logger.debug("GDS projection '%s' dropped", graph_name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to drop GDS projection '%s': %s", graph_name, exc
                    )
