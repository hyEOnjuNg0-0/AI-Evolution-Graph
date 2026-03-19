"""Unit tests for Neo4jGraphRepository using a mocked Neo4j driver."""

from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from aievograph.domain.models import Author, Citation, Method, MethodRelation, Paper
from aievograph.infrastructure.neo4j_graph_repository import (
    Neo4jGraphRepository,
    _CREATE_CITATION,
    _CREATE_INDEXES,
    _CREATE_METHOD_RELATION_TEMPLATE,
    _CREATE_PAPER_USES_METHOD,
    _GET_PAPERS_BY_YEAR_RANGE,
    _UPSERT_METHOD,
    _UPSERT_PAPER,
    _record_to_paper,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_driver() -> tuple[MagicMock, MagicMock]:
    """Return (driver_mock, session_mock) with session as a context manager."""
    session = MagicMock()
    driver = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session


def _make_paper(
    paper_id: str = "P1",
    title: str = "Test Paper",
    year: int = 2022,
    refs: tuple[str, ...] = (),
) -> Paper:
    return Paper(
        paper_id=paper_id,
        title=title,
        publication_year=year,
        venue="NeurIPS",
        citation_count=50,
        reference_count=len(refs),
        referenced_work_ids=refs,
        authors=[Author(author_id="A1", name="Alice")],
    )


# ---------------------------------------------------------------------------
# create_indexes
# ---------------------------------------------------------------------------

class TestCreateIndexes:
    def test_runs_all_index_statements(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)
        repo.create_indexes()

        run_calls = session.run.call_args_list
        cypher_calls = [c[0][0] for c in run_calls]
        assert cypher_calls == _CREATE_INDEXES

    def test_opens_one_session(self) -> None:
        driver, _ = _make_driver()
        repo = Neo4jGraphRepository(driver)
        repo.create_indexes()
        assert driver.session.call_count == 1


# ---------------------------------------------------------------------------
# upsert_paper
# ---------------------------------------------------------------------------

class TestUpsertPaper:
    def test_runs_upsert_query(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)
        paper = _make_paper()

        repo.upsert_paper(paper)

        session.run.assert_called_once()
        cypher = session.run.call_args[0][0]
        assert cypher == _UPSERT_PAPER

    def test_passes_correct_params(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)
        paper = _make_paper(paper_id="P42", title="Deep Learning", year=2021)

        repo.upsert_paper(paper)

        kwargs = session.run.call_args[1]
        assert kwargs["paper_id"] == "P42"
        assert kwargs["title"] == "Deep Learning"
        assert kwargs["publication_year"] == 2021
        assert kwargs["venue"] == "NeurIPS"
        assert kwargs["citation_count"] == 50
        assert kwargs["authors"] == [{"author_id": "A1", "name": "Alice"}]

    def test_passes_empty_authors(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)
        paper = Paper(
            paper_id="P1", title="No Authors", publication_year=2020, authors=[]
        )
        repo.upsert_paper(paper)
        kwargs = session.run.call_args[1]
        assert kwargs["authors"] == []


# ---------------------------------------------------------------------------
# upsert_method
# ---------------------------------------------------------------------------

class TestUpsertMethod:
    def test_runs_method_query(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)
        method = Method(name="Transformer", method_type="Model", description="Attention")

        repo.upsert_method(method)

        cypher = session.run.call_args[0][0]
        assert cypher == _UPSERT_METHOD
        kwargs = session.run.call_args[1]
        assert kwargs["name"] == "Transformer"
        assert kwargs["method_type"] == "Model"
        assert kwargs["description"] == "Attention"


# ---------------------------------------------------------------------------
# create_citation
# ---------------------------------------------------------------------------

class TestCreateCitation:
    def test_runs_citation_query(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)
        citation = Citation(citing_paper_id="P1", cited_paper_id="P2", created_year=2022)

        repo.create_citation(citation)

        cypher = session.run.call_args[0][0]
        assert cypher == _CREATE_CITATION

    def test_passes_correct_params(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)
        citation = Citation(citing_paper_id="P1", cited_paper_id="P2", created_year=2022)

        repo.create_citation(citation)

        kwargs = session.run.call_args[1]
        assert kwargs["citing_paper_id"] == "P1"
        assert kwargs["cited_paper_id"] == "P2"
        assert kwargs["created_year"] == 2022


# ---------------------------------------------------------------------------
# get_papers_by_year_range
# ---------------------------------------------------------------------------

class TestGetPapersByYearRange:
    def _make_neo4j_record(self, paper_id: str, year: int) -> MagicMock:
        """Simulate a Neo4j record with a Paper node and an Author node."""
        paper_node = MagicMock()
        paper_node.__getitem__ = MagicMock(side_effect={
            "paper_id": paper_id,
            "title": f"Paper {paper_id}",
            "publication_year": year,
        }.__getitem__)
        paper_node.get = MagicMock(side_effect=lambda k, d=None: {
            "paper_id": paper_id,
            "title": f"Paper {paper_id}",
            "publication_year": year,
            "venue": "ICML",
            "abstract": None,
            "citation_count": 10,
            "reference_count": 2,
        }.get(k, d))

        author_node = MagicMock()
        author_node.__getitem__ = MagicMock(side_effect={
            "author_id": "A1",
            "name": "Alice",
        }.__getitem__)
        author_node.get = MagicMock(side_effect=lambda k, d=None: {
            "author_id": "A1",
            "name": "Alice",
        }.get(k, d))

        record = MagicMock()
        record.__getitem__ = MagicMock(side_effect={"p": paper_node, "authors": [author_node]}.__getitem__)
        return record

    def test_runs_year_range_query(self) -> None:
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jGraphRepository(driver)

        repo.get_papers_by_year_range(2020, 2023)

        cypher = session.run.call_args[0][0]
        assert cypher == _GET_PAPERS_BY_YEAR_RANGE

    def test_passes_year_params(self) -> None:
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jGraphRepository(driver)

        repo.get_papers_by_year_range(2018, 2022)

        kwargs = session.run.call_args[1]
        assert kwargs["start_year"] == 2018
        assert kwargs["end_year"] == 2022

    def test_passes_empty_venues_when_none(self) -> None:
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jGraphRepository(driver)

        repo.get_papers_by_year_range(2018, 2022)

        kwargs = session.run.call_args[1]
        assert kwargs["venues"] == []

    def test_passes_venues_when_provided(self) -> None:
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jGraphRepository(driver)

        repo.get_papers_by_year_range(2018, 2022, venues=["NeurIPS", "ICML"])

        kwargs = session.run.call_args[1]
        assert kwargs["venues"] == ["NeurIPS", "ICML"]

    def test_returns_empty_list_when_no_results(self) -> None:
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jGraphRepository(driver)

        result = repo.get_papers_by_year_range(2020, 2022)

        assert result == []

    def test_returns_paper_list(self) -> None:
        driver, session = _make_driver()
        records = [self._make_neo4j_record("P1", 2021)]
        session.run.return_value = records
        repo = Neo4jGraphRepository(driver)

        papers = repo.get_papers_by_year_range(2020, 2022)

        assert len(papers) == 1
        assert papers[0].paper_id == "P1"
        assert papers[0].publication_year == 2021
        assert len(papers[0].authors) == 1
        assert papers[0].authors[0].name == "Alice"


# ---------------------------------------------------------------------------
# _record_to_paper (helper)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# create_method_relation
# ---------------------------------------------------------------------------

class TestCreateMethodRelation:
    def _make_relation(self, rtype: str = "IMPROVES") -> MethodRelation:
        return MethodRelation(
            source_method="BERT",
            target_method="RoBERTa",
            relation_type=rtype,  # type: ignore[arg-type]
            evidence="RoBERTa improves BERT pre-training.",
        )

    def test_runs_query_with_correct_relation_type(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)
        relation = self._make_relation("IMPROVES")

        repo.create_method_relation(relation)

        cypher = session.run.call_args[0][0]
        assert "IMPROVES" in cypher

    def test_query_is_derived_from_template(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)
        relation = self._make_relation("EXTENDS")

        repo.create_method_relation(relation)

        expected = _CREATE_METHOD_RELATION_TEMPLATE.format(relation_type="EXTENDS")
        cypher = session.run.call_args[0][0]
        assert cypher == expected

    def test_passes_correct_params(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)
        relation = self._make_relation("REPLACES")

        repo.create_method_relation(relation)

        kwargs = session.run.call_args[1]
        assert kwargs["source_method"] == "BERT"
        assert kwargs["target_method"] == "RoBERTa"
        assert kwargs["evidence"] == "RoBERTa improves BERT pre-training."

    def test_all_relation_types_are_accepted(self) -> None:
        for rtype in ("IMPROVES", "EXTENDS", "REPLACES"):
            driver, session = _make_driver()
            repo = Neo4jGraphRepository(driver)
            repo.create_method_relation(self._make_relation(rtype))
            cypher = session.run.call_args[0][0]
            assert rtype in cypher


# ---------------------------------------------------------------------------
# create_paper_uses_method
# ---------------------------------------------------------------------------

class TestCreatePaperUsesMethod:
    def test_runs_uses_query(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)

        repo.create_paper_uses_method("P1", "BERT")

        cypher = session.run.call_args[0][0]
        assert cypher == _CREATE_PAPER_USES_METHOD

    def test_passes_correct_params(self) -> None:
        driver, session = _make_driver()
        repo = Neo4jGraphRepository(driver)

        repo.create_paper_uses_method("P42", "Transformer")

        kwargs = session.run.call_args[1]
        assert kwargs["paper_id"] == "P42"
        assert kwargs["method_name"] == "Transformer"


# ---------------------------------------------------------------------------
# _record_to_paper (helper)
# ---------------------------------------------------------------------------

class TestRecordToPaper:
    def _make_record(
        self,
        paper_id: str = "P1",
        year: int = 2022,
        authors: list[dict[str, str]] | None = None,
    ) -> MagicMock:
        if authors is None:
            authors = [{"author_id": "A1", "name": "Alice"}]

        paper_node = MagicMock()
        paper_node.__getitem__ = MagicMock(side_effect={
            "paper_id": paper_id,
            "title": "T",
            "publication_year": year,
        }.__getitem__)
        paper_node.get = MagicMock(side_effect=lambda k, d=None: {
            "venue": None,
            "abstract": None,
            "citation_count": 0,
            "reference_count": 0,
        }.get(k, d))

        author_nodes = []
        for a in authors:
            node = MagicMock()
            node.__getitem__ = MagicMock(side_effect=a.__getitem__)
            node.get = MagicMock(side_effect=lambda k, d=None, _a=a: _a.get(k, d))
            author_nodes.append(node)

        record = MagicMock()
        record.__getitem__ = MagicMock(
            side_effect={"p": paper_node, "authors": author_nodes}.__getitem__
        )
        return record

    def test_none_author_is_skipped(self) -> None:
        paper_node = MagicMock()
        paper_node.get = MagicMock(side_effect=lambda k, d=None: {
            "paper_id": "P1", "title": "T", "publication_year": 2022,
        }.get(k, d))

        record = MagicMock()
        record.__getitem__ = MagicMock(
            side_effect={"p": paper_node, "authors": [None]}.__getitem__
        )

        paper = _record_to_paper(record)
        assert paper.authors == []
