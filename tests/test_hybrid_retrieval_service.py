"""Unit tests for HybridRetrievalService."""

from unittest.mock import MagicMock

import pytest

from aievograph.domain.models import Paper, ScoredPaper, Subgraph
from aievograph.domain.services.hybrid_retrieval_service import (
    _MAX_HOPS,
    _QUERY_WEIGHTS,
    _graph_proximity,
    HybridRetrievalService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paper(paper_id: str) -> Paper:
    return Paper(paper_id=paper_id, title=f"Title {paper_id}", publication_year=2020)


def _make_scored_paper(paper_id: str, score: float) -> ScoredPaper:
    return ScoredPaper(paper=_make_paper(paper_id), score=score)


@pytest.fixture()
def vector_service():
    return MagicMock()


@pytest.fixture()
def graph_repo():
    return MagicMock()


@pytest.fixture()
def service(vector_service, graph_repo):
    return HybridRetrievalService(vector_service=vector_service, graph_repo=graph_repo)


# ---------------------------------------------------------------------------
# _graph_proximity helper
# ---------------------------------------------------------------------------

class TestGraphProximity:
    def test_hop_zero_returns_one(self):
        assert _graph_proximity(0) == 1.0

    def test_hop_one_returns_one(self):
        assert _graph_proximity(1) == 1.0

    def test_hop_two_returns_half(self):
        assert _graph_proximity(2) == pytest.approx(0.5)

    def test_hop_three_returns_third(self):
        assert _graph_proximity(3) == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# HybridRetrievalService.search — input validation
# ---------------------------------------------------------------------------

class TestSearchValidation:
    def test_raises_on_empty_query(self, service):
        with pytest.raises(ValueError, match="query must not be empty"):
            service.search("")

    def test_raises_on_whitespace_query(self, service):
        with pytest.raises(ValueError, match="query must not be empty"):
            service.search("   ")

    def test_raises_on_invalid_query_type(self, service):
        with pytest.raises(ValueError, match="query_type"):
            service.search("query", query_type="unknown")  # type: ignore[arg-type]

    def test_raises_on_zero_top_k(self, service):
        with pytest.raises(ValueError, match="top_k"):
            service.search("query", top_k=0)

    def test_raises_on_negative_top_k(self, service):
        with pytest.raises(ValueError, match="top_k"):
            service.search("query", top_k=-1)

    def test_raises_on_zero_hops(self, service):
        with pytest.raises(ValueError, match="hops"):
            service.search("query", hops=0)

    def test_raises_on_negative_hops(self, service):
        with pytest.raises(ValueError, match="hops"):
            service.search("query", hops=-1)

    def test_raises_on_hops_exceeding_max(self, service):
        with pytest.raises(ValueError, match="hops"):
            service.search("query", hops=_MAX_HOPS + 1)

    def test_accepts_max_hops(self, service, vector_service, graph_repo):
        vector_service.search.return_value = []
        result = service.search("query", hops=_MAX_HOPS)
        assert isinstance(result, Subgraph)

    def test_raises_on_negative_alpha(self, service):
        with pytest.raises(ValueError, match="alpha"):
            service.search("query", alpha=-0.1)

    def test_raises_on_alpha_greater_than_one(self, service):
        with pytest.raises(ValueError, match="alpha"):
            service.search("query", alpha=1.1)

    def test_raises_on_negative_beta(self, service):
        with pytest.raises(ValueError, match="beta"):
            service.search("query", beta=-0.1)

    def test_raises_on_beta_greater_than_one(self, service):
        with pytest.raises(ValueError, match="beta"):
            service.search("query", beta=1.1)

    def test_raises_on_both_weights_zero(self, service):
        with pytest.raises(ValueError, match="alpha \\+ beta"):
            service.search("query", alpha=0.0, beta=0.0)


# ---------------------------------------------------------------------------
# HybridRetrievalService.search — output type
# ---------------------------------------------------------------------------

class TestSearchOutputType:
    def test_returns_subgraph(self, service, vector_service, graph_repo):
        vector_service.search.return_value = []
        result = service.search("query")
        assert isinstance(result, Subgraph)

    def test_empty_vector_results_returns_empty_subgraph(
        self, service, vector_service, graph_repo
    ):
        vector_service.search.return_value = []
        result = service.search("query")
        assert result.papers == []
        graph_repo.get_citation_neighborhood_with_distances.assert_not_called()


# ---------------------------------------------------------------------------
# HybridRetrievalService.search — scoring
# ---------------------------------------------------------------------------

class TestSearchScoring:
    def test_seed_gets_semantic_score_and_graph_proximity_one(
        self, service, vector_service, graph_repo
    ):
        sp = _make_scored_paper("seed", score=0.8)
        vector_service.search.return_value = [sp]
        graph_repo.get_citation_neighborhood_with_distances.return_value = []

        result = service.search("query", query_type="balanced", alpha=0.5, beta=0.5)

        # hybrid = 0.5 * 0.8 + 0.5 * _graph_proximity(0) = 0.4 + 0.5 = 0.9
        assert len(result.papers) == 1
        assert result.papers[0].score == pytest.approx(0.9)

    def test_graph_only_paper_has_zero_semantic_similarity(
        self, service, vector_service, graph_repo
    ):
        sp = _make_scored_paper("seed", score=0.8)
        vector_service.search.return_value = [sp]
        neighbor = (_make_paper("neighbor"), 1)
        graph_repo.get_citation_neighborhood_with_distances.return_value = [neighbor]

        result = service.search("query", query_type="balanced", alpha=0.5, beta=0.5)

        neighbor_result = next(p for p in result.papers if p.paper.paper_id == "neighbor")
        # hybrid = 0.5 * 0.0 + 0.5 * _graph_proximity(1) = 0.0 + 0.5 = 0.5
        assert neighbor_result.score == pytest.approx(0.5)

    def test_paper_in_both_uses_semantic_score_and_graph_proximity(
        self, service, vector_service, graph_repo
    ):
        # "shared" appears in both vector results and as a graph neighbor of "seed"
        sp_seed = _make_scored_paper("seed", score=0.9)
        sp_shared = _make_scored_paper("shared", score=0.6)
        vector_service.search.return_value = [sp_seed, sp_shared]
        # "seed" expands to "shared" at hop 1 — "shared" distance stays 0 (it's also a seed)
        graph_repo.get_citation_neighborhood_with_distances.side_effect = [
            [(_make_paper("shared"), 1)],  # seed's neighbors
            [],                            # shared's neighbors
        ]

        result = service.search("query", query_type="balanced", alpha=0.5, beta=0.5)

        shared_result = next(p for p in result.papers if p.paper.paper_id == "shared")
        # "shared" is a seed (hop=0), so graph_prox = 1.0
        # hybrid = 0.5 * 0.6 + 0.5 * 1.0 = 0.8
        assert shared_result.score == pytest.approx(0.8)

    def test_minimum_hop_distance_used_across_seeds(
        self, service, vector_service, graph_repo
    ):
        sp1 = _make_scored_paper("seed1", score=0.5)
        sp2 = _make_scored_paper("seed2", score=0.5)
        vector_service.search.return_value = [sp1, sp2]
        # "common" appears at hop 2 from seed1 and hop 1 from seed2 → min = 1
        graph_repo.get_citation_neighborhood_with_distances.side_effect = [
            [(_make_paper("common"), 2)],  # seed1 neighbors
            [(_make_paper("common"), 1)],  # seed2 neighbors
        ]

        result = service.search("query", query_type="balanced", alpha=0.5, beta=0.5)

        common = next(p for p in result.papers if p.paper.paper_id == "common")
        # min hop = 1 → graph_prox = 1.0 → hybrid = 0.5 * 0.0 + 0.5 * 1.0 = 0.5
        assert common.score == pytest.approx(0.5)

    def test_results_sorted_by_score_descending(self, service, vector_service, graph_repo):
        vector_service.search.return_value = [
            _make_scored_paper("p1", score=0.3),
            _make_scored_paper("p2", score=0.9),
            _make_scored_paper("p3", score=0.6),
        ]
        graph_repo.get_citation_neighborhood_with_distances.return_value = []

        result = service.search("query", query_type="balanced")

        scores = [p.score for p in result.papers]
        assert scores == sorted(scores, reverse=True)

    def test_returns_at_most_top_k_papers(self, service, vector_service, graph_repo):
        vector_service.search.return_value = [
            _make_scored_paper(f"p{i}", score=float(i) / 10) for i in range(5)
        ]
        graph_repo.get_citation_neighborhood_with_distances.return_value = []

        result = service.search("query", top_k=3)

        assert len(result.papers) <= 3

    def test_tiebreaker_is_deterministic(self, service, vector_service, graph_repo):
        # Two papers with identical scores must always come out in the same order.
        vector_service.search.return_value = [
            _make_scored_paper("zzz", score=0.5),
            _make_scored_paper("aaa", score=0.5),
        ]
        graph_repo.get_citation_neighborhood_with_distances.return_value = []

        r1 = service.search("query", query_type="balanced")
        r2 = service.search("query", query_type="balanced")

        assert [p.paper.paper_id for p in r1.papers] == [p.paper.paper_id for p in r2.papers]


# ---------------------------------------------------------------------------
# HybridRetrievalService.search — query type weights
# ---------------------------------------------------------------------------

class TestQueryTypeWeights:
    def _run_with_type(self, service, vector_service, graph_repo, query_type: str) -> float:
        """Return hybrid score for a seed paper with semantic_sim=1.0."""
        vector_service.search.return_value = [_make_scored_paper("p", score=1.0)]
        graph_repo.get_citation_neighborhood_with_distances.return_value = []
        result = service.search("query", query_type=query_type)  # type: ignore[arg-type]
        return result.papers[0].score

    def test_semantic_type_weights(self, service, vector_service, graph_repo):
        a, b = _QUERY_WEIGHTS["semantic"]
        score = self._run_with_type(service, vector_service, graph_repo, "semantic")
        # semantic_sim=1.0, graph_prox=1.0 (seed)
        assert score == pytest.approx(a * 1.0 + b * 1.0)

    def test_structural_type_weights(self, service, vector_service, graph_repo):
        a, b = _QUERY_WEIGHTS["structural"]
        score = self._run_with_type(service, vector_service, graph_repo, "structural")
        assert score == pytest.approx(a * 1.0 + b * 1.0)

    def test_balanced_type_weights(self, service, vector_service, graph_repo):
        a, b = _QUERY_WEIGHTS["balanced"]
        score = self._run_with_type(service, vector_service, graph_repo, "balanced")
        assert score == pytest.approx(a * 1.0 + b * 1.0)

    def test_alpha_beta_override_ignores_query_type_defaults(
        self, service, vector_service, graph_repo
    ):
        vector_service.search.return_value = [_make_scored_paper("p", score=0.4)]
        graph_repo.get_citation_neighborhood_with_distances.return_value = []

        result = service.search("query", query_type="semantic", alpha=0.0, beta=1.0)

        # With alpha=0, beta=1: score = 0*0.4 + 1*1.0 = 1.0
        assert result.papers[0].score == pytest.approx(1.0)
