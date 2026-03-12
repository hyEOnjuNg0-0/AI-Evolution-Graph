"""Unit tests for CitationGraphService."""

from unittest.mock import MagicMock, call

import pytest

from aievograph.domain.models import Author, Citation, Paper
from aievograph.domain.services.citation_graph_service import CitationGraphService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paper(
    paper_id: str,
    year: int = 2022,
    refs: tuple[str, ...] = (),
) -> Paper:
    return Paper(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        publication_year=year,
        referenced_work_ids=refs,
    )


def _make_repo() -> MagicMock:
    repo = MagicMock()
    repo.create_indexes = MagicMock()
    repo.upsert_paper = MagicMock()
    repo.create_citation = MagicMock()
    return repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildCitationGraph:
    def test_calls_create_indexes_first(self) -> None:
        repo = _make_repo()
        service = CitationGraphService(repo)
        call_order: list[str] = []
        repo.create_indexes.side_effect = lambda: call_order.append("indexes")
        repo.upsert_paper.side_effect = lambda p: call_order.append("paper")

        service.build_citation_graph([_make_paper("P1")])

        assert call_order[0] == "indexes"

    def test_upserts_all_papers(self) -> None:
        repo = _make_repo()
        service = CitationGraphService(repo)
        papers = [_make_paper("P1"), _make_paper("P2"), _make_paper("P3")]

        service.build_citation_graph(papers)

        assert repo.upsert_paper.call_count == 3
        upserted_ids = {c.args[0].paper_id for c in repo.upsert_paper.call_args_list}
        assert upserted_ids == {"P1", "P2", "P3"}

    def test_creates_citation_between_collected_papers(self) -> None:
        repo = _make_repo()
        service = CitationGraphService(repo)
        # P1 cites P2; both are in the collected set
        papers = [_make_paper("P1", refs=("P2",)), _make_paper("P2")]

        service.build_citation_graph(papers)

        repo.create_citation.assert_called_once()
        citation: Citation = repo.create_citation.call_args[0][0]
        assert citation.citing_paper_id == "P1"
        assert citation.cited_paper_id == "P2"
        assert citation.created_year == 2022

    def test_skips_citations_to_uncollected_papers(self) -> None:
        repo = _make_repo()
        service = CitationGraphService(repo)
        # P1 references EXTERNAL which is not in the collection
        papers = [_make_paper("P1", refs=("EXTERNAL",)), _make_paper("P2")]

        service.build_citation_graph(papers)

        repo.create_citation.assert_not_called()

    def test_multiple_citations_from_one_paper(self) -> None:
        repo = _make_repo()
        service = CitationGraphService(repo)
        papers = [
            _make_paper("P1", refs=("P2", "P3")),
            _make_paper("P2"),
            _make_paper("P3"),
        ]

        service.build_citation_graph(papers)

        assert repo.create_citation.call_count == 2
        cited_ids = {c.args[0].cited_paper_id for c in repo.create_citation.call_args_list}
        assert cited_ids == {"P2", "P3"}

    def test_empty_paper_list(self) -> None:
        repo = _make_repo()
        service = CitationGraphService(repo)

        service.build_citation_graph([])

        repo.create_indexes.assert_called_once()
        repo.upsert_paper.assert_not_called()
        repo.create_citation.assert_not_called()

    def test_citation_uses_citing_paper_year(self) -> None:
        repo = _make_repo()
        service = CitationGraphService(repo)
        papers = [_make_paper("P1", year=2019, refs=("P2",)), _make_paper("P2", year=2015)]

        service.build_citation_graph(papers)

        citation: Citation = repo.create_citation.call_args[0][0]
        assert citation.created_year == 2019  # year of the citing paper

    def test_partial_refs_in_collection(self) -> None:
        """Only references to papers in the collected set become edges."""
        repo = _make_repo()
        service = CitationGraphService(repo)
        papers = [
            _make_paper("P1", refs=("P2", "OUTSIDE1", "P3", "OUTSIDE2")),
            _make_paper("P2"),
            _make_paper("P3"),
        ]

        service.build_citation_graph(papers)

        assert repo.create_citation.call_count == 2
        cited_ids = {c.args[0].cited_paper_id for c in repo.create_citation.call_args_list}
        assert cited_ids == {"P2", "P3"}
