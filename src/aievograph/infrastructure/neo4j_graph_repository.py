"""
Neo4j driver
        ↓
Neo4jGraphRepository  (implements GraphRepositoryPort)
        ↓
  upsert_paper            → (:Paper)-[:WRITTEN_BY]->(:Author)
  upsert_method           → (:Method)
  create_citation         → (:Paper)-[:CITES]->(:Paper)
  create_method_relation  → (:Method)-[:IMPROVES|EXTENDS|REPLACES]->(:Method)
  create_paper_uses_method→ (:Paper)-[:USES]->(:Method)
  get_papers_by_year_range → list[Paper]
"""

import logging
from typing import Any

from neo4j import Driver

from aievograph.domain.models import Citation, Method, MethodRelation, Paper
from aievograph.domain.ports.graph_repository import GraphRepositoryPort
from aievograph.infrastructure.neo4j_utils import record_to_paper as _record_to_paper_util

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
AND (size($venues) = 0 OR p.venue IN $venues)
OPTIONAL MATCH (p)-[:WRITTEN_BY]->(a:Author)
RETURN p, collect(a) AS authors
ORDER BY p.publication_year
"""

# Dynamic relation type — safe because MethodRelation.relation_type is a validated Literal
_CREATE_METHOD_RELATION_TEMPLATE = """\
MATCH (src:Method {{name: $source_method}})
MATCH (tgt:Method {{name: $target_method}})
MERGE (src)-[r:{relation_type}]->(tgt)
SET r.evidence = $evidence
"""

_CREATE_PAPER_USES_METHOD = """
MATCH (p:Paper {paper_id: $paper_id})
MATCH (m:Method {name: $method_name})
MERGE (p)-[:USES]->(m)
"""

_GET_PAPER_BY_ID = """
MATCH (p:Paper {paper_id: $paper_id})
OPTIONAL MATCH (p)-[:WRITTEN_BY]->(a:Author)
RETURN p, collect(a) AS authors
"""

# hops is a validated positive integer embedded as a literal — not a parameter.
# Cypher does not support parameterized path lengths (e.g. *1..$hops).
# $limit caps result set size to prevent unbounded memory use on large graphs.
_GET_CITATION_NEIGHBORHOOD_TEMPLATE = """\
MATCH (seed:Paper {{paper_id: $paper_id}})
MATCH (seed)-[:CITES*1..{hops}]-(neighbor:Paper)
WHERE neighbor.paper_id <> $paper_id
WITH DISTINCT neighbor AS p
OPTIONAL MATCH (p)-[:WRITTEN_BY]->(a:Author)
RETURN p, collect(a) AS authors
LIMIT $limit
"""

# Returns the minimum hop distance to each neighbor across all paths.
_GET_NEIGHBORHOOD_WITH_DISTANCES_TEMPLATE = """\
MATCH (seed:Paper {{paper_id: $paper_id}})
MATCH path = (seed)-[:CITES*1..{hops}]-(neighbor:Paper)
WHERE neighbor.paper_id <> $paper_id
WITH neighbor, min(length(path)) AS hop_dist
OPTIONAL MATCH (neighbor)-[:WRITTEN_BY]->(a:Author)
WITH neighbor AS p, hop_dist, collect(a) AS authors
RETURN p, authors, hop_dist
LIMIT $limit
"""

_MAX_RESULT_PAPERS = 1000

# Safety cap for batched neighborhood expansion across all seeds.
# With hops=1 and 200 seeds, ~50 neighbours/seed ≈ 10 000 rows in practice.
_MAX_BATCH_RESULT_PAPERS = 50_000

# hops embedded as a literal (Cypher does not support parameterised path lengths).
# $paper_ids is a list of seed IDs; each row carries seed_id so results can be grouped.
_GET_NEIGHBORHOODS_BATCH_TEMPLATE = """\
UNWIND $paper_ids AS seed_id
MATCH (seed:Paper {{paper_id: seed_id}})
MATCH path = (seed)-[:CITES*1..{hops}]-(neighbor:Paper)
WHERE neighbor.paper_id <> seed_id
WITH seed_id, neighbor, min(length(path)) AS hop_dist
OPTIONAL MATCH (neighbor)-[:WRITTEN_BY]->(a:Author)
RETURN seed_id, neighbor AS p, collect(a) AS authors, hop_dist
LIMIT $limit
"""

_GET_ALL_METHOD_NAMES = "MATCH (m:Method) RETURN m.name AS name ORDER BY m.name"

# Re-point all edges from variant to canonical, then delete variant.
# All steps run inside a single explicit transaction (see merge_method_nodes).
# Self-loop prevention:
#   - incoming Method steps (2-4): WHERE src.name <> $canonical AND src.name <> $variant
#   - outgoing steps (5-7): WHERE tgt.name <> $variant AND tgt.name <> $canonical
# Evidence preservation (steps 2-7):
#   Edges are collected as {node, evidence} pairs; COALESCE keeps an existing
#   evidence value when canonical already has an edge, and fills in the variant's
#   evidence only when the edge is newly created.
# Step 8 MATCHes canonical first so that a missing canonical aborts the delete.
_MERGE_METHOD_NODES_STEPS = [
    # 1. incoming USES: (:Paper)-[:USES]->(variant) → (:Paper)-[:USES]->(canonical)
    #    Paper nodes cannot be canonical/variant so no self-loop risk here.
    """
MATCH (canonical:Method {name: $canonical})
MATCH (variant:Method  {name: $variant})
OPTIONAL MATCH (p:Paper)-[:USES]->(variant)
WITH canonical, collect(p) AS papers
FOREACH (p IN papers | MERGE (p)-[:USES]->(canonical))
""",
    # 2. incoming IMPROVES: (:src:Method)-[:IMPROVES]->(variant) → (:src)-[:IMPROVES]->(canonical)
    #    Skip if src IS canonical to prevent (canonical)-[:IMPROVES]->(canonical) self-loop.
    #    Collect (src, evidence) pairs so the evidence property is carried to the new edge.
    #    COALESCE keeps the existing evidence if canonical already has an edge from src.
    """
MATCH (canonical:Method {name: $canonical})
MATCH (variant:Method  {name: $variant})
OPTIONAL MATCH (src:Method)-[r:IMPROVES]->(variant)
WHERE src.name <> $canonical AND src.name <> $variant
WITH canonical, collect({src: src, evidence: r.evidence}) AS raw
UNWIND [p IN raw WHERE p.src IS NOT NULL] AS pair
WITH canonical, pair.src AS src_node, pair.evidence AS ev
MERGE (src_node)-[nr:IMPROVES]->(canonical)
SET nr.evidence = COALESCE(nr.evidence, ev)
""",
    # 3. incoming EXTENDS
    """
MATCH (canonical:Method {name: $canonical})
MATCH (variant:Method  {name: $variant})
OPTIONAL MATCH (src:Method)-[r:EXTENDS]->(variant)
WHERE src.name <> $canonical AND src.name <> $variant
WITH canonical, collect({src: src, evidence: r.evidence}) AS raw
UNWIND [p IN raw WHERE p.src IS NOT NULL] AS pair
WITH canonical, pair.src AS src_node, pair.evidence AS ev
MERGE (src_node)-[nr:EXTENDS]->(canonical)
SET nr.evidence = COALESCE(nr.evidence, ev)
""",
    # 4. incoming REPLACES
    """
MATCH (canonical:Method {name: $canonical})
MATCH (variant:Method  {name: $variant})
OPTIONAL MATCH (src:Method)-[r:REPLACES]->(variant)
WHERE src.name <> $canonical AND src.name <> $variant
WITH canonical, collect({src: src, evidence: r.evidence}) AS raw
UNWIND [p IN raw WHERE p.src IS NOT NULL] AS pair
WITH canonical, pair.src AS src_node, pair.evidence AS ev
MERGE (src_node)-[nr:REPLACES]->(canonical)
SET nr.evidence = COALESCE(nr.evidence, ev)
""",
    # 5. outgoing IMPROVES: (variant)-[:IMPROVES]->(tgt) → (canonical)-[:IMPROVES]->(tgt)
    #    Skip self-loops: tgt must not be variant or canonical.
    #    Collect (tgt, evidence) pairs so the evidence property is carried to the new edge.
    """
MATCH (canonical:Method {name: $canonical})
MATCH (variant:Method  {name: $variant})
OPTIONAL MATCH (variant)-[r:IMPROVES]->(tgt:Method)
WHERE tgt.name <> $variant AND tgt.name <> $canonical
WITH canonical, collect({tgt: tgt, evidence: r.evidence}) AS raw
UNWIND [p IN raw WHERE p.tgt IS NOT NULL] AS pair
WITH canonical, pair.tgt AS tgt_node, pair.evidence AS ev
MERGE (canonical)-[nr:IMPROVES]->(tgt_node)
SET nr.evidence = COALESCE(nr.evidence, ev)
""",
    # 6. outgoing EXTENDS
    """
MATCH (canonical:Method {name: $canonical})
MATCH (variant:Method  {name: $variant})
OPTIONAL MATCH (variant)-[r:EXTENDS]->(tgt:Method)
WHERE tgt.name <> $variant AND tgt.name <> $canonical
WITH canonical, collect({tgt: tgt, evidence: r.evidence}) AS raw
UNWIND [p IN raw WHERE p.tgt IS NOT NULL] AS pair
WITH canonical, pair.tgt AS tgt_node, pair.evidence AS ev
MERGE (canonical)-[nr:EXTENDS]->(tgt_node)
SET nr.evidence = COALESCE(nr.evidence, ev)
""",
    # 7. outgoing REPLACES
    """
MATCH (canonical:Method {name: $canonical})
MATCH (variant:Method  {name: $variant})
OPTIONAL MATCH (variant)-[r:REPLACES]->(tgt:Method)
WHERE tgt.name <> $variant AND tgt.name <> $canonical
WITH canonical, collect({tgt: tgt, evidence: r.evidence}) AS raw
UNWIND [p IN raw WHERE p.tgt IS NOT NULL] AS pair
WITH canonical, pair.tgt AS tgt_node, pair.evidence AS ev
MERGE (canonical)-[nr:REPLACES]->(tgt_node)
SET nr.evidence = COALESCE(nr.evidence, ev)
""",
    # 8. Delete variant. Requires canonical to exist — if canonical is absent the
    #    MATCH fails and the delete is skipped, preventing silent data loss.
    """
MATCH (canonical:Method {name: $canonical})
MATCH (variant:Method  {name: $variant})
DETACH DELETE variant
""",
]


def _record_to_paper(record: Any) -> Paper:
    """Convert a Neo4j record to a Paper domain object.

    Thin wrapper around the shared utility in neo4j_utils so that callers
    (including existing tests) that import this name continue to work.
    """
    return _record_to_paper_util(record)


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

    def get_papers_by_year_range(
        self, start_year: int, end_year: int, venues: list[str] | None = None
    ) -> list[Paper]:
        with self._driver.session() as session:
            result = session.run(
                _GET_PAPERS_BY_YEAR_RANGE,
                start_year=start_year,
                end_year=end_year,
                venues=venues or [],
            )
            return [_record_to_paper(record) for record in result]

    def create_method_relation(self, relation: MethodRelation) -> None:
        cypher = _CREATE_METHOD_RELATION_TEMPLATE.format(relation_type=relation.relation_type)
        with self._driver.session() as session:
            session.run(
                cypher,
                source_method=relation.source_method,
                target_method=relation.target_method,
                evidence=relation.evidence,
            )
        logger.debug(
            "Created method relation: %s -[%s]-> %s",
            relation.source_method,
            relation.relation_type,
            relation.target_method,
        )

    def create_paper_uses_method(self, paper_id: str, method_name: str) -> None:
        with self._driver.session() as session:
            session.run(
                _CREATE_PAPER_USES_METHOD,
                paper_id=paper_id,
                method_name=method_name,
            )
        logger.debug("Created USES edge: %s -> %s", paper_id, method_name)

    def get_paper_by_id(self, paper_id: str) -> Paper | None:
        with self._driver.session() as session:
            result = session.run(_GET_PAPER_BY_ID, paper_id=paper_id)
            record = result.single()
        if record is None:
            return None
        return _record_to_paper(record)

    def get_citation_neighborhood(self, paper_id: str, hops: int) -> list[Paper]:
        # int() cast guards against accidental string injection into the format template.
        cypher = _GET_CITATION_NEIGHBORHOOD_TEMPLATE.format(hops=int(hops))
        with self._driver.session() as session:
            result = session.run(cypher, paper_id=paper_id, limit=_MAX_RESULT_PAPERS)
            return [_record_to_paper(record) for record in result]

    def get_citation_neighborhood_with_distances(
        self, paper_id: str, hops: int
    ) -> list[tuple[Paper, int]]:
        cypher = _GET_NEIGHBORHOOD_WITH_DISTANCES_TEMPLATE.format(hops=int(hops))
        with self._driver.session() as session:
            result = session.run(cypher, paper_id=paper_id, limit=_MAX_RESULT_PAPERS)
            return [(_record_to_paper(record), record["hop_dist"]) for record in result]

    def get_citation_neighborhoods_batch(
        self, paper_ids: list[str], hops: int
    ) -> dict[str, list[tuple[Paper, int]]]:
        if not paper_ids:
            return {}
        cypher = _GET_NEIGHBORHOODS_BATCH_TEMPLATE.format(hops=int(hops))
        result_map: dict[str, list[tuple[Paper, int]]] = {}
        with self._driver.session() as session:
            result = session.run(cypher, paper_ids=paper_ids, limit=_MAX_BATCH_RESULT_PAPERS)
            for record in result:
                seed_id: str = record["seed_id"]
                paper = _record_to_paper(record)
                hop_dist: int = record["hop_dist"]
                result_map.setdefault(seed_id, []).append((paper, hop_dist))
        return result_map

    def get_all_method_names(self) -> list[str]:
        with self._driver.session() as session:
            result = session.run(_GET_ALL_METHOD_NAMES)
            return [record["name"] for record in result]

    def merge_method_nodes(self, canonical_name: str, variant_name: str) -> None:
        """Re-point all edges from variant to canonical, then delete the variant node.

        All 8 steps run in a single explicit write transaction so that a mid-step
        failure rolls back the entire operation and leaves the graph consistent.
        Raises ValueError if the canonical node does not exist.
        """
        def _tx(tx) -> None:
            # Fail fast: canonical must exist before any edge is moved.
            result = tx.run(
                "MATCH (m:Method {name: $name}) RETURN count(m) AS cnt",
                name=canonical_name,
            )
            if result.single()["cnt"] == 0:
                raise ValueError(
                    f"Canonical method node '{canonical_name}' not found in the graph."
                )
            for step in _MERGE_METHOD_NODES_STEPS:
                tx.run(step, canonical=canonical_name, variant=variant_name)

        with self._driver.session() as session:
            session.execute_write(_tx)
        logger.debug("Merged method node '%s' into '%s'.", variant_name, canonical_name)
