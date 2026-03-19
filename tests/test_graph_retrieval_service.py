"""Unit tests for GraphRetrievalService."""

from unittest.mock import MagicMock

import pytest

from aievograph.domain.models import Paper
from aievograph.domain.services.graph_retrieval_service import (
    _DEFAULT_HOPS,
    _MAX_HOPS,
    GraphRetrievalService,
)


def _make_paper(paper_id: str) -> Paper:
    return Paper(paper_id=paper_id, title=f"Title {paper_id}", publication_year=2020)


@pytest.fixture()
def graph_repo():
    return MagicMock()


@pytest.fixture()
def service(graph_repo):
    return GraphRetrievalService(graph_repo=graph_repo)


class TestExpandFromId:
    def test_returns_neighbors_from_repo(self, service, graph_repo):
        seed = _make_paper("seed")
        neighbors = [_make_paper("p1"), _make_paper("p2")]
        graph_repo.get_paper_by_id.return_value = seed
        graph_repo.get_citation_neighborhood.return_value = neighbors

        result = service.expand_from_id("seed", hops=1)

        assert result == neighbors

    def test_delegates_correct_args_to_repo(self, service, graph_repo):
        graph_repo.get_paper_by_id.return_value = _make_paper("seed")
        graph_repo.get_citation_neighborhood.return_value = []

        service.expand_from_id("seed", hops=3)

        graph_repo.get_citation_neighborhood.assert_called_once_with("seed", 3)

    def test_default_hops_is_one(self, service, graph_repo):
        graph_repo.get_paper_by_id.return_value = _make_paper("seed")
        graph_repo.get_citation_neighborhood.return_value = []

        service.expand_from_id("seed")

        _, call_hops = graph_repo.get_citation_neighborhood.call_args.args
        assert call_hops == _DEFAULT_HOPS

    def test_returns_empty_list_when_no_neighbors(self, service, graph_repo):
        graph_repo.get_paper_by_id.return_value = _make_paper("seed")
        graph_repo.get_citation_neighborhood.return_value = []

        result = service.expand_from_id("seed")

        assert result == []

    def test_raises_on_empty_paper_id(self, service):
        with pytest.raises(ValueError, match="paper_id must not be empty"):
            service.expand_from_id("")

    def test_raises_on_whitespace_paper_id(self, service):
        with pytest.raises(ValueError, match="paper_id must not be empty"):
            service.expand_from_id("   ")

    def test_raises_on_zero_hops(self, service):
        with pytest.raises(ValueError, match="hops"):
            service.expand_from_id("seed", hops=0)

    def test_raises_on_negative_hops(self, service):
        with pytest.raises(ValueError, match="hops"):
            service.expand_from_id("seed", hops=-1)

    def test_raises_when_seed_not_found(self, service, graph_repo):
        graph_repo.get_paper_by_id.return_value = None

        with pytest.raises(ValueError, match="Paper not found"):
            service.expand_from_id("nonexistent")

    def test_does_not_call_neighborhood_when_seed_missing(self, service, graph_repo):
        graph_repo.get_paper_by_id.return_value = None

        with pytest.raises(ValueError):
            service.expand_from_id("nonexistent")

        graph_repo.get_citation_neighborhood.assert_not_called()

    def test_multi_hop_result_forwarded_as_is(self, service, graph_repo):
        papers = [_make_paper(f"p{i}") for i in range(5)]
        graph_repo.get_paper_by_id.return_value = _make_paper("seed")
        graph_repo.get_citation_neighborhood.return_value = papers

        result = service.expand_from_id("seed", hops=2)

        assert len(result) == 5

    def test_raises_on_hops_exceeding_max(self, service):
        with pytest.raises(ValueError, match="hops"):
            service.expand_from_id("seed", hops=_MAX_HOPS + 1)

    def test_accepts_max_hops(self, service, graph_repo):
        graph_repo.get_paper_by_id.return_value = _make_paper("seed")
        graph_repo.get_citation_neighborhood.return_value = []

        # Should not raise
        service.expand_from_id("seed", hops=_MAX_HOPS)

    def test_excludes_seed_from_results(self, service, graph_repo):
        # Repo mistakenly returns seed among neighbors
        seed = _make_paper("seed")
        graph_repo.get_paper_by_id.return_value = seed
        graph_repo.get_citation_neighborhood.return_value = [
            _make_paper("p1"),
            seed,  # seed included by repo
            _make_paper("p2"),
        ]

        result = service.expand_from_id("seed")

        assert all(p.paper_id != "seed" for p in result)
        assert len(result) == 2
