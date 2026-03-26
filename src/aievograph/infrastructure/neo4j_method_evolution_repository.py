"""
neo4j.Driver
        ↓
Neo4jMethodEvolutionRepository  (implements MethodEvolutionRepositoryPort)
        ↓
  get_relations(method_names)
      → list[(source, target, relation_type)]   -- method graph edges
  get_paper_methods(paper_ids)
      → dict[paper_id, list[method_name]]       -- paper→method mapping
"""

import logging

from neo4j import Driver

from aievograph.domain.ports.method_evolution_repository import MethodEvolutionRepositoryPort

logger = logging.getLogger(__name__)

# Fetch IMPROVES/EXTENDS/REPLACES edges where both endpoints are in the requested set.
_METHOD_RELATIONS = """
MATCH (src:Method)-[r]->(tgt:Method)
WHERE src.name IN $method_names
  AND tgt.name IN $method_names
  AND type(r) IN ['IMPROVES', 'EXTENDS', 'REPLACES']
RETURN src.name AS source, tgt.name AS target, type(r) AS relation_type
"""

# For each paper in paper_ids, return the methods it uses.
_PAPER_METHODS = """
MATCH (p:Paper)-[:USES]->(m:Method)
WHERE p.paper_id IN $paper_ids
RETURN p.paper_id AS paper_id, m.name AS method_name
"""


class Neo4jMethodEvolutionRepository(MethodEvolutionRepositoryPort):
    """Fetch Method Evolution Graph structure from Neo4j."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def get_relations(
        self,
        method_names: list[str],
    ) -> list[tuple[str, str, str]]:
        """Return method-relation edges within the requested method subgraph."""
        if not method_names:
            return []

        results: list[tuple[str, str, str]] = []
        with self._driver.session() as session:
            for r in session.run(_METHOD_RELATIONS, method_names=method_names):
                results.append((r["source"], r["target"], r["relation_type"]))

        logger.debug(
            "Method relations fetched: %d edges for %d methods",
            len(results),
            len(method_names),
        )
        return results

    def get_paper_methods(
        self,
        paper_ids: list[str],
    ) -> dict[str, list[str]]:
        """Return methods used by each paper in paper_ids."""
        if not paper_ids:
            return {}

        result: dict[str, list[str]] = {}
        with self._driver.session() as session:
            for r in session.run(_PAPER_METHODS, paper_ids=paper_ids):
                pid = r["paper_id"]
                method_name = r["method_name"]
                if pid not in result:
                    result[pid] = []
                result[pid].append(method_name)

        logger.debug(
            "Paper-method mapping fetched: %d/%d papers have USES edges",
            len(result),
            len(paper_ids),
        )
        return result
