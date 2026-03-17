"""
Integration test: Semantic Scholar data → Neo4j pipeline.

Requirements:
  - A running Neo4j instance reachable via NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
  - Run with: pytest -m integration

Each test uses its own isolated set of paper IDs to avoid cross-test interference.
The teardown fixture removes all nodes created during the test.
"""

import os
from unittest.mock import MagicMock

import pytest
from neo4j import GraphDatabase

from aievograph.domain.models import Author, Citation, ExtractionResult, Method, MethodRelation, NormalizationMap, Paper
from aievograph.domain.services.citation_graph_service import CitationGraphService
from aievograph.domain.services.entity_normalization_service import EntityNormalizationService
from aievograph.domain.services.method_extraction_service import MethodExtractionService
from aievograph.domain.services.method_graph_service import MethodGraphService
from aievograph.infrastructure.neo4j_graph_repository import Neo4jGraphRepository

# ---------------------------------------------------------------------------
# Fixture: Neo4j driver (skips test if env vars are absent)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def neo4j_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    if not password:
        pytest.skip("NEO4J_PASSWORD not set — skipping integration tests.")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    yield driver
    driver.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup(driver, paper_ids: list[str]) -> None:
    """Remove test Paper nodes and their Author nodes (if no other paper references them)."""
    with driver.session() as session:
        session.run(
            "MATCH (p:Paper) WHERE p.paper_id IN $ids DETACH DELETE p",
            ids=paper_ids,
        )


def _make_paper(
    paper_id: str,
    year: int = 2022,
    refs: tuple[str, ...] = (),
) -> Paper:
    return Paper(
        paper_id=paper_id,
        title=f"Integration Paper {paper_id}",
        publication_year=year,
        venue="NeurIPS",
        citation_count=10,
        reference_count=len(refs),
        referenced_work_ids=refs,
        authors=[Author(author_id=f"AUTH_{paper_id}", name=f"Author of {paper_id}")],
    )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestNeo4jGraphRepositoryIntegration:
    def test_upsert_and_retrieve_paper(self, neo4j_driver) -> None:
        paper_ids = ["INT_P1"]
        repo = Neo4jGraphRepository(neo4j_driver)
        try:
            repo.create_indexes()
            repo.upsert_paper(_make_paper("INT_P1", year=2021))

            papers = repo.get_papers_by_year_range(2021, 2021)
            matching = [p for p in papers if p.paper_id == "INT_P1"]
            assert len(matching) == 1
            assert matching[0].title == "Integration Paper INT_P1"
            assert matching[0].publication_year == 2021
        finally:
            _cleanup(neo4j_driver, paper_ids)

    def test_upsert_is_idempotent(self, neo4j_driver) -> None:
        paper_ids = ["INT_P2"]
        repo = Neo4jGraphRepository(neo4j_driver)
        try:
            repo.create_indexes()
            repo.upsert_paper(_make_paper("INT_P2", year=2020))
            repo.upsert_paper(_make_paper("INT_P2", year=2020))  # second upsert

            with neo4j_driver.session() as session:
                result = session.run(
                    "MATCH (p:Paper {paper_id: 'INT_P2'}) RETURN count(p) AS cnt"
                )
                assert result.single()["cnt"] == 1
        finally:
            _cleanup(neo4j_driver, paper_ids)

    def test_create_citation_edge(self, neo4j_driver) -> None:
        paper_ids = ["INT_C1", "INT_C2"]
        repo = Neo4jGraphRepository(neo4j_driver)
        try:
            repo.create_indexes()
            repo.upsert_paper(_make_paper("INT_C1", year=2022))
            repo.upsert_paper(_make_paper("INT_C2", year=2020))
            repo.create_citation(
                Citation(citing_paper_id="INT_C1", cited_paper_id="INT_C2", created_year=2022)
            )

            with neo4j_driver.session() as session:
                result = session.run(
                    """
                    MATCH (a:Paper {paper_id: 'INT_C1'})-[r:CITES]->(b:Paper {paper_id: 'INT_C2'})
                    RETURN count(r) AS cnt
                    """
                )
                assert result.single()["cnt"] == 1
        finally:
            _cleanup(neo4j_driver, paper_ids)

    def test_year_range_filter(self, neo4j_driver) -> None:
        paper_ids = ["INT_Y2019", "INT_Y2020", "INT_Y2021"]
        repo = Neo4jGraphRepository(neo4j_driver)
        try:
            repo.create_indexes()
            for pid, yr in [("INT_Y2019", 2019), ("INT_Y2020", 2020), ("INT_Y2021", 2021)]:
                repo.upsert_paper(_make_paper(pid, year=yr))

            papers = repo.get_papers_by_year_range(2020, 2021)
            matching_ids = {p.paper_id for p in papers if p.paper_id.startswith("INT_Y")}
            assert matching_ids == {"INT_Y2020", "INT_Y2021"}
        finally:
            _cleanup(neo4j_driver, paper_ids)


@pytest.mark.integration
class TestCitationGraphServiceIntegration:
    def test_full_pipeline(self, neo4j_driver) -> None:
        """build_citation_graph creates nodes + CITES edges end-to-end."""
        paper_ids = ["INT_SVC1", "INT_SVC2", "INT_SVC3"]
        repo = Neo4jGraphRepository(neo4j_driver)
        service = CitationGraphService(repo)

        papers = [
            _make_paper("INT_SVC1", year=2022, refs=("INT_SVC2", "INT_SVC3")),
            _make_paper("INT_SVC2", year=2020),
            _make_paper("INT_SVC3", year=2019),
        ]

        try:
            service.build_citation_graph(papers)

            with neo4j_driver.session() as session:
                # Verify Paper nodes
                result = session.run(
                    "MATCH (p:Paper) WHERE p.paper_id IN $ids RETURN count(p) AS cnt",
                    ids=paper_ids,
                )
                assert result.single()["cnt"] == 3

                # Verify CITES edges from INT_SVC1
                result = session.run(
                    """
                    MATCH (:Paper {paper_id: 'INT_SVC1'})-[:CITES]->(cited:Paper)
                    RETURN collect(cited.paper_id) AS cited_ids
                    """
                )
                cited_ids = set(result.single()["cited_ids"])
                assert cited_ids == {"INT_SVC2", "INT_SVC3"}

            # Verify year-range query
            papers_2020_2022 = repo.get_papers_by_year_range(2020, 2022)
            matching = {p.paper_id for p in papers_2020_2022 if p.paper_id.startswith("INT_SVC")}
            assert matching == {"INT_SVC1", "INT_SVC2"}
        finally:
            _cleanup(neo4j_driver, paper_ids)

    def test_external_refs_not_added_as_nodes(self, neo4j_driver) -> None:
        """References to papers outside the collected set must not create Paper nodes."""
        paper_ids = ["INT_EXT1"]
        repo = Neo4jGraphRepository(neo4j_driver)
        service = CitationGraphService(repo)

        papers = [_make_paper("INT_EXT1", refs=("OUTSIDE_PAPER",))]
        try:
            service.build_citation_graph(papers)

            with neo4j_driver.session() as session:
                result = session.run(
                    "MATCH (p:Paper {paper_id: 'OUTSIDE_PAPER'}) RETURN count(p) AS cnt"
                )
                assert result.single()["cnt"] == 0
        finally:
            _cleanup(neo4j_driver, paper_ids)


# ---------------------------------------------------------------------------
# Integration tests: MethodGraphService
# ---------------------------------------------------------------------------

def _cleanup_methods(driver, method_names: list[str]) -> None:
    """Remove test Method nodes."""
    with driver.session() as session:
        session.run(
            "MATCH (m:Method) WHERE m.name IN $names DETACH DELETE m",
            names=method_names,
        )


def _make_stub_extraction_service(
    results: list[tuple[str, ExtractionResult]],
) -> MethodExtractionService:
    """Return a MethodExtractionService backed by a stub extractor."""
    extractor = MagicMock()
    extractor.extract.return_value = ExtractionResult()  # unused — extract_from_papers is mocked
    service = MagicMock(spec=MethodExtractionService)
    service.extract_from_papers.return_value = results
    return service


def _make_stub_normalization_service(
    results: list[tuple[str, ExtractionResult]],
) -> EntityNormalizationService:
    """Return an EntityNormalizationService that returns results unchanged."""
    service = MagicMock(spec=EntityNormalizationService)
    service.normalize.return_value = (results, NormalizationMap())
    return service


@pytest.mark.integration
class TestMethodGraphServiceIntegration:
    def test_method_nodes_are_created(self, neo4j_driver) -> None:
        """upsert_method via build_method_graph creates Method nodes in Neo4j."""
        method_names = ["INT_BERT", "INT_RoBERTa"]
        paper_ids = ["INT_MP1"]
        repo = Neo4jGraphRepository(neo4j_driver)

        extraction_results = [
            (
                "INT_MP1",
                ExtractionResult(
                    methods=[
                        Method(name="INT_BERT", method_type="Model"),
                        Method(name="INT_RoBERTa", method_type="Model"),
                    ]
                ),
            )
        ]
        service = MethodGraphService(
            repo,
            _make_stub_extraction_service(extraction_results),
            _make_stub_normalization_service(extraction_results),
        )
        paper = Paper(
            paper_id="INT_MP1",
            title="Method Graph Paper",
            publication_year=2022,
            abstract="Uses BERT and RoBERTa.",
        )
        repo.upsert_paper(paper)

        try:
            service.build_method_graph([paper])

            with neo4j_driver.session() as session:
                result = session.run(
                    "MATCH (m:Method) WHERE m.name IN $names RETURN count(m) AS cnt",
                    names=method_names,
                )
                assert result.single()["cnt"] == 2
        finally:
            _cleanup(neo4j_driver, paper_ids)
            _cleanup_methods(neo4j_driver, method_names)

    def test_uses_edges_are_created(self, neo4j_driver) -> None:
        """build_method_graph creates (:Paper)-[:USES]->(:Method) edges."""
        method_names = ["INT_Transformer"]
        paper_ids = ["INT_MP2"]
        repo = Neo4jGraphRepository(neo4j_driver)

        extraction_results = [
            ("INT_MP2", ExtractionResult(methods=[Method(name="INT_Transformer", method_type="Model")])),
        ]
        service = MethodGraphService(
            repo,
            _make_stub_extraction_service(extraction_results),
            _make_stub_normalization_service(extraction_results),
        )
        paper = Paper(
            paper_id="INT_MP2",
            title="Transformer Paper",
            publication_year=2017,
            abstract="Introduces the Transformer.",
        )
        repo.upsert_paper(paper)

        try:
            service.build_method_graph([paper])

            with neo4j_driver.session() as session:
                result = session.run(
                    """
                    MATCH (:Paper {paper_id: 'INT_MP2'})-[:USES]->(m:Method {name: 'INT_Transformer'})
                    RETURN count(m) AS cnt
                    """
                )
                assert result.single()["cnt"] == 1
        finally:
            _cleanup(neo4j_driver, paper_ids)
            _cleanup_methods(neo4j_driver, method_names)

    def test_method_relation_edges_are_created(self, neo4j_driver) -> None:
        """build_method_graph creates typed IMPROVES edges between Method nodes."""
        method_names = ["INT_GPT2", "INT_GPT3"]
        paper_ids = ["INT_MP3"]
        repo = Neo4jGraphRepository(neo4j_driver)

        relation = MethodRelation(
            source_method="INT_GPT3",
            target_method="INT_GPT2",
            relation_type="IMPROVES",
            evidence="GPT-3 improves upon GPT-2.",
        )
        extraction_results = [
            (
                "INT_MP3",
                ExtractionResult(
                    methods=[
                        Method(name="INT_GPT2", method_type="Model"),
                        Method(name="INT_GPT3", method_type="Model"),
                    ],
                    relations=[relation],
                ),
            )
        ]
        service = MethodGraphService(
            repo,
            _make_stub_extraction_service(extraction_results),
            _make_stub_normalization_service(extraction_results),
        )
        paper = Paper(
            paper_id="INT_MP3",
            title="GPT-3 Paper",
            publication_year=2020,
            abstract="GPT-3 improves upon GPT-2.",
        )
        repo.upsert_paper(paper)

        try:
            service.build_method_graph([paper])

            with neo4j_driver.session() as session:
                result = session.run(
                    """
                    MATCH (:Method {name: 'INT_GPT3'})-[r:IMPROVES]->(:Method {name: 'INT_GPT2'})
                    RETURN count(r) AS cnt, r.evidence AS ev
                    """
                )
                record = result.single()
                assert record["cnt"] == 1
                assert record["ev"] == "GPT-3 improves upon GPT-2."
        finally:
            _cleanup(neo4j_driver, paper_ids)
            _cleanup_methods(neo4j_driver, method_names)
