"""Unit tests for CentralityRankingService (Layer C Step 4.1)."""

import pytest

from aievograph.domain.models import (
    CentralityScores,
    Paper,
    ScoredPaper,
    Subgraph,
)
from aievograph.domain.ports.centrality_repository import CentralityRepositoryPort
from aievograph.domain.services.centrality_ranking_service import (
    CentralityRankingService,
    _normalize,
)


# ---------------------------------------------------------------------------
# Stub
# ---------------------------------------------------------------------------

class StubCentralityRepo(CentralityRepositoryPort):
    """Deterministic stub: returns pre-set pagerank/betweenness dicts."""

    def __init__(
        self,
        pagerank: dict[str, float],
        betweenness: dict[str, float],
    ) -> None:
        self._pr = pagerank
        self._bw = betweenness

    def compute_centralities(
        self, paper_ids: list[str]
    ) -> tuple[dict[str, float], dict[str, float]]:
        return self._pr, self._bw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paper(paper_id: str) -> Paper:
    return Paper(paper_id=paper_id, title=f"Paper {paper_id}", publication_year=2020)


def _make_subgraph(*paper_ids: str) -> Subgraph:
    return Subgraph(
        papers=[ScoredPaper(paper=_make_paper(pid), score=0.5) for pid in paper_ids]
    )


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_empty_dict_returns_empty(self):
        assert _normalize({}) == {}

    def test_all_zeros_returns_zeros(self):
        assert _normalize({"a": 0.0, "b": 0.0}) == {"a": 0.0, "b": 0.0}

    def test_max_value_becomes_one(self):
        result = _normalize({"a": 2.0, "b": 1.0})
        assert result["a"] == pytest.approx(1.0)
        assert result["b"] == pytest.approx(0.5)

    def test_negative_values_clipped_to_zero(self):
        result = _normalize({"a": 4.0, "b": -2.0})
        assert result["a"] == pytest.approx(1.0)
        assert result["b"] == pytest.approx(0.0)

    def test_all_negative_returns_zeros(self):
        result = _normalize({"a": -1.0, "b": -3.0})
        assert result == {"a": 0.0, "b": 0.0}

    def test_single_entry(self):
        assert _normalize({"x": 5.0}) == {"x": pytest.approx(1.0)}


# ---------------------------------------------------------------------------
# CentralityRankingService.rank()
# ---------------------------------------------------------------------------

class TestRank:
    def _service(self, pr: dict, bw: dict) -> CentralityRankingService:
        return CentralityRankingService(StubCentralityRepo(pr, bw))

    def test_empty_subgraph_returns_empty_list(self):
        svc = self._service({}, {})
        result = svc.rank(Subgraph())
        assert result == []

    def test_invalid_gamma_raises(self):
        svc = self._service({}, {})
        with pytest.raises(ValueError, match="gamma"):
            svc.rank(_make_subgraph("p1"), gamma=-0.1)
        with pytest.raises(ValueError, match="gamma"):
            svc.rank(_make_subgraph("p1"), gamma=1.1)

    def test_returns_scored_papers_sorted_descending(self):
        svc = self._service(
            pr={"p1": 1.0, "p2": 0.5},
            bw={"p1": 0.0, "p2": 1.0},
        )
        # gamma=1.0 → pure pagerank: p1(1.0) > p2(0.5)
        result = svc.rank(_make_subgraph("p1", "p2"), gamma=1.0)
        assert [sp.paper.paper_id for sp in result] == ["p1", "p2"]

    def test_gamma_zero_uses_only_betweenness(self):
        svc = self._service(
            pr={"p1": 1.0, "p2": 0.0},
            bw={"p1": 0.0, "p2": 1.0},
        )
        result = svc.rank(_make_subgraph("p1", "p2"), gamma=0.0)
        assert result[0].paper.paper_id == "p2"
        assert result[0].score == pytest.approx(1.0)

    def test_gamma_one_uses_only_pagerank(self):
        svc = self._service(
            pr={"p1": 0.0, "p2": 1.0},
            bw={"p1": 1.0, "p2": 0.0},
        )
        result = svc.rank(_make_subgraph("p1", "p2"), gamma=1.0)
        assert result[0].paper.paper_id == "p2"
        assert result[0].score == pytest.approx(1.0)

    def test_missing_paper_from_repo_defaults_to_zero(self):
        # Repo returns scores only for p1; p2 must default to 0.0.
        svc = self._service(pr={"p1": 1.0}, bw={"p1": 0.5})
        result = svc.rank(_make_subgraph("p1", "p2"), gamma=1.0)
        p2 = next(sp for sp in result if sp.paper.paper_id == "p2")
        assert p2.score == pytest.approx(0.0)

    def test_score_is_non_negative(self):
        svc = self._service(
            pr={"p1": -5.0, "p2": 2.0},
            bw={"p1": 0.0, "p2": 0.0},
        )
        result = svc.rank(_make_subgraph("p1", "p2"), gamma=1.0)
        for sp in result:
            assert sp.score >= 0.0

    def test_tiebreaker_is_paper_id_ascending(self):
        # Both papers get identical combined score → paper_id tiebreaker.
        svc = self._service(
            pr={"p_b": 1.0, "p_a": 1.0},
            bw={"p_b": 1.0, "p_a": 1.0},
        )
        result = svc.rank(_make_subgraph("p_b", "p_a"), gamma=0.5)
        assert result[0].paper.paper_id == "p_a"

    def test_combined_score_formula(self):
        svc = self._service(
            pr={"p1": 1.0},
            bw={"p1": 1.0},
        )
        result = svc.rank(_make_subgraph("p1"), gamma=0.7)
        # Both normalized to 1.0 → 0.7×1 + 0.3×1 = 1.0
        assert result[0].score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# CentralityRankingService.score_breakdown()
# ---------------------------------------------------------------------------

class TestScoreBreakdown:
    def _service(self, pr: dict, bw: dict) -> CentralityRankingService:
        return CentralityRankingService(StubCentralityRepo(pr, bw))

    def test_returns_centrality_scores_type(self):
        svc = self._service(pr={"p1": 1.0}, bw={"p1": 0.5})
        result = svc.score_breakdown(_make_subgraph("p1"))
        assert all(isinstance(c, CentralityScores) for c in result)

    def test_individual_scores_populated(self):
        svc = self._service(
            pr={"p1": 2.0, "p2": 1.0},
            bw={"p1": 0.0, "p2": 4.0},
        )
        result = svc.score_breakdown(_make_subgraph("p1", "p2"), gamma=0.5)
        by_id = {c.paper_id: c for c in result}

        assert by_id["p1"].pagerank == pytest.approx(1.0)   # 2/2
        assert by_id["p1"].betweenness == pytest.approx(0.0) # 0/4
        assert by_id["p2"].pagerank == pytest.approx(0.5)   # 1/2
        assert by_id["p2"].betweenness == pytest.approx(1.0) # 4/4

    def test_empty_subgraph_returns_empty_list(self):
        svc = self._service({}, {})
        assert svc.score_breakdown(Subgraph()) == []

    def test_invalid_gamma_raises(self):
        svc = self._service({}, {})
        with pytest.raises(ValueError, match="gamma"):
            svc.score_breakdown(_make_subgraph("p1"), gamma=2.0)


# ---------------------------------------------------------------------------
# Subgraph uniqueness guard (model-level)
# ---------------------------------------------------------------------------

class TestSubgraphUniqueness:
    def test_duplicate_paper_id_raises(self):
        paper = _make_paper("dup")
        sp = ScoredPaper(paper=paper, score=0.5)
        with pytest.raises(ValueError, match="Duplicate paper_id"):
            Subgraph(papers=[sp, sp])

    def test_unique_paper_ids_accepted(self):
        subgraph = _make_subgraph("p1", "p2", "p3")
        assert len(subgraph.papers) == 3
