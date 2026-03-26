"""
neo4j.Driver
        ↓
Neo4jCentralityRepository  (implements CentralityRepositoryPort)
        ↓
  compute_centralities(paper_ids)
      → (pagerank: dict[str, float], betweenness: dict[str, float])

Pure-Cypher degree approximations (no GDS plugin required):
  - PageRank proxy  : in-degree within the subgraph (citation count)
  - Betweenness proxy: in-degree × out-degree within the subgraph

Works on AuraDB Free and any Neo4j instance without GDS.
Accuracy is sufficient for small-to-medium citation subgraphs.
"""

import logging

from neo4j import Driver

from aievograph.domain.ports.centrality_repository import CentralityRepositoryPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

# in-degree within the subgraph → PageRank proxy
_IN_DEGREE = """
MATCH (n:Paper) WHERE n.paper_id IN $paper_ids
OPTIONAL MATCH (src:Paper)-[:CITES]->(n) WHERE src.paper_id IN $paper_ids
RETURN n.paper_id AS paper_id, count(src) AS in_deg
"""

# out-degree within the subgraph → needed for betweenness proxy
_OUT_DEGREE = """
MATCH (n:Paper) WHERE n.paper_id IN $paper_ids
OPTIONAL MATCH (n)-[:CITES]->(dst:Paper) WHERE dst.paper_id IN $paper_ids
RETURN n.paper_id AS paper_id, count(dst) AS out_deg
"""


class Neo4jCentralityRepository(CentralityRepositoryPort):
    """Compute subgraph-scoped centrality metrics using pure Cypher degree counts.

    Replaces the GDS-based implementation so the code works on AuraDB Free
    and any Neo4j instance that does not have the GDS plugin installed.
    """

    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def compute_centralities(
        self, paper_ids: list[str]
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Compute PageRank and Betweenness proxies via degree counts.

        PageRank proxy  = in-degree  (number of citations received within subgraph)
        Betweenness proxy = in-degree × out-degree  (bridge-node heuristic)

        Returns:
            (pagerank_scores, betweenness_scores) — both dicts map paper_id → raw score.
        """
        if not paper_ids:
            return {}, {}

        with self._driver.session() as session:
            in_deg: dict[str, float] = {
                r["paper_id"]: float(r["in_deg"])
                for r in session.run(_IN_DEGREE, paper_ids=paper_ids)
                if r["paper_id"] is not None
            }
            out_deg: dict[str, float] = {
                r["paper_id"]: float(r["out_deg"])
                for r in session.run(_OUT_DEGREE, paper_ids=paper_ids)
                if r["paper_id"] is not None
            }

        logger.debug(
            "Degree centrality computed for %d papers (in_deg=%d, out_deg=%d)",
            len(paper_ids),
            len(in_deg),
            len(out_deg),
        )

        pagerank = in_deg

        betweenness: dict[str, float] = {
            pid: in_deg.get(pid, 0.0) * out_deg.get(pid, 0.0)
            for pid in paper_ids
        }

        return pagerank, betweenness
