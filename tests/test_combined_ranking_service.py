"""Unit tests for CombinedRankingService and _extract_backbone_paths (Layer C Step 4.3)."""

import pytest

from aievograph.domain.models import (
    CentralityScores,
    Paper,
    RankingResult,
    ScoredPaper,
    Subgraph,
)
from aievograph.domain.ports.subgraph_edge_repository import SubgraphEdgeRepositoryPort
from aievograph.domain.services.centrality_ranking_service import CentralityRankingService
from aievograph.domain.services.combined_ranking_service import (
    CombinedRankingService,
    _DEFAULT_ALPHA,
    _extract_backbone_paths,
)
from aievograph.domain.services.embedding_ranking_service import EmbeddingRankingService
from aievograph.domain.ports.centrality_repository import CentralityRepositoryPort
from aievograph.domain.ports.paper_embedding_repository import PaperEmbeddingRepositoryPort
from aievograph.domain.ports.embedding_port import EmbeddingPort


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class StubCentralityRepo(CentralityRepositoryPort):
    def __init__(self, pr: dict[str, float], bw: dict[str, float]) -> None:
        self._pr = pr
        self._bw = bw

    def compute_centralities(
        self, paper_ids: list[str]
    ) -> tuple[dict[str, float], dict[str, float]]:
        return self._pr, self._bw


class StubEmbeddingPort(EmbeddingPort):
    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    def embed(self, text: str) -> list[float]:
        return self._vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._vector for _ in texts]


class StubPaperEmbeddingRepo(PaperEmbeddingRepositoryPort):
    def __init__(self, embeddings: dict[str, list[float]]) -> None:
        self._embeddings = embeddings

    def get_embeddings(self, paper_ids: list[str]) -> dict[str, list[float]]:
        return {pid: self._embeddings[pid] for pid in paper_ids if pid in self._embeddings}


class StubEdgeRepo(SubgraphEdgeRepositoryPort):
    def __init__(self, edges: list[tuple[str, str]]) -> None:
        self._edges = edges

    def get_citation_edges(self, paper_ids: list[str]) -> list[tuple[str, str]]:
        ids = set(paper_ids)
        return [(a, b) for a, b in self._edges if a in ids and b in ids]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paper(paper_id: str) -> Paper:
    return Paper(paper_id=paper_id, title=f"Paper {paper_id}", publication_year=2020)


def _make_subgraph(*paper_ids: str) -> Subgraph:
    return Subgraph(
        papers=[ScoredPaper(paper=_make_paper(pid), score=0.5) for pid in paper_ids]
    )


def _unit_vector(dim: int, index: int) -> list[float]:
    """Return a unit vector with 1.0 at position `index`, 0.0 elsewhere."""
    v = [0.0] * dim
    v[index] = 1.0
    return v


def _make_service(
    pr: dict[str, float],
    bw: dict[str, float],
    paper_embeddings: dict[str, list[float]],
    query_vector: list[float],
    edges: list[tuple[str, str]],
) -> CombinedRankingService:
    centrality_svc = CentralityRankingService(StubCentralityRepo(pr, bw))
    embedding_svc = EmbeddingRankingService(
        StubEmbeddingPort(query_vector),
        StubPaperEmbeddingRepo(paper_embeddings),
    )
    return CombinedRankingService(centrality_svc, embedding_svc, StubEdgeRepo(edges))


# ---------------------------------------------------------------------------
# _extract_backbone_paths
# ---------------------------------------------------------------------------

class TestExtractBackbonePaths:
    def test_no_edges_returns_empty(self):
        result = _extract_backbone_paths({"p1", "p2"}, [], {"p1": 1.0, "p2": 0.5})
        assert result == []

    def test_single_edge_forms_path(self):
        # p1 cites p2 → research flow: p2 → p1
        result = _extract_backbone_paths(
            {"p1", "p2"},
            [("p1", "p2")],  # p1 citing p2
            {"p1": 1.0, "p2": 0.8},
        )
        assert result == [["p2", "p1"]]

    def test_linear_chain(self):
        # p3 cites p2 cites p1 → flow: p1 → p2 → p3
        edges = [("p2", "p1"), ("p3", "p2")]
        result = _extract_backbone_paths(
            {"p1", "p2", "p3"}, edges, {"p1": 1.0, "p2": 1.0, "p3": 1.0}
        )
        assert result == [["p1", "p2", "p3"]]

    def test_branching_paths(self):
        # p2 cites p1, p3 cites p1 → two paths from p1
        edges = [("p2", "p1"), ("p3", "p1")]
        result = _extract_backbone_paths(
            {"p1", "p2", "p3"}, edges, {"p1": 1.0, "p2": 0.8, "p3": 0.6}
        )
        paths_as_sets = [tuple(p) for p in result]
        assert ("p1", "p2") in paths_as_sets
        assert ("p1", "p3") in paths_as_sets

    def test_min_length_two_filters_isolated_roots(self):
        # p1 has no successors → not a path
        result = _extract_backbone_paths(
            {"p1"}, [], {"p1": 1.0}
        )
        assert result == []

    def test_cycle_does_not_infinite_loop(self):
        # Artificially create a cycle: p1→p2→p3→p1 (citing direction)
        edges = [("p2", "p1"), ("p3", "p2"), ("p1", "p3")]
        # Should terminate without hanging; result may be empty or partial paths
        result = _extract_backbone_paths(
            {"p1", "p2", "p3"}, edges, {"p1": 1.0, "p2": 1.0, "p3": 1.0}
        )
        assert isinstance(result, list)

    def test_sorted_by_mean_score_descending(self):
        # Two chains: p1→p2 (mean=1.0) and p3→p4 (mean=0.2)
        edges = [("p2", "p1"), ("p4", "p3")]
        scores = {"p1": 1.0, "p2": 1.0, "p3": 0.2, "p4": 0.2}
        result = _extract_backbone_paths({"p1", "p2", "p3", "p4"}, edges, scores)
        assert result[0] == ["p1", "p2"]
        assert result[1] == ["p3", "p4"]

    def test_self_loop_edge_ignored(self):
        # Self-loop should not be added to adjacency.
        result = _extract_backbone_paths(
            {"p1"}, [("p1", "p1")], {"p1": 1.0}
        )
        assert result == []

    def test_diamond_dag_produces_two_paths(self):
        # p4 cites p2 and p3; p2 and p3 both cite p1 (diamond / foundational-paper pattern).
        # Research flow: p1 → p2 → p4 and p1 → p3 → p4.
        edges = [("p2", "p1"), ("p3", "p1"), ("p4", "p2"), ("p4", "p3")]
        result = _extract_backbone_paths(
            {"p1", "p2", "p3", "p4"},
            edges,
            {"p1": 1.0, "p2": 0.8, "p3": 0.6, "p4": 0.9},
        )
        paths_as_tuples = {tuple(p) for p in result}
        assert ("p1", "p2", "p4") in paths_as_tuples
        assert ("p1", "p3", "p4") in paths_as_tuples

    def test_partial_cycle_terminates_and_yields_path(self):
        # p2 cites p1 (p1 is source), p3 cites p2, p2 cites p3 (cycle between p2 and p3).
        # visited guard should cut the cycle; path [p1, p2, p3] should be recorded.
        edges = [("p2", "p1"), ("p3", "p2"), ("p2", "p3")]
        result = _extract_backbone_paths(
            {"p1", "p2", "p3"},
            edges,
            {"p1": 1.0, "p2": 1.0, "p3": 1.0},
        )
        assert ["p1", "p2", "p3"] in result

    def test_equal_mean_score_order_is_deterministic(self):
        # Two chains with identical mean scores; result order must be stable
        # regardless of PYTHONHASHSEED (i.e. not depend on set iteration order).
        edges = [("p2", "p1"), ("p4", "p3")]
        scores = {"p1": 1.0, "p2": 1.0, "p3": 1.0, "p4": 1.0}
        result1 = _extract_backbone_paths({"p1", "p2", "p3", "p4"}, edges, scores)
        result2 = _extract_backbone_paths({"p1", "p2", "p3", "p4"}, edges, scores)
        assert result1 == result2
        # Lexicographic tiebreaker: ["p1","p2"] < ["p3","p4"]
        assert result1 == [["p1", "p2"], ["p3", "p4"]]


# ---------------------------------------------------------------------------
# CombinedRankingService.rank()
# ---------------------------------------------------------------------------

class TestCombinedRankingService:
    def test_empty_subgraph_returns_empty_result(self):
        svc = _make_service({}, {}, {}, [0.0], [])
        result = svc.rank("query", Subgraph())
        assert isinstance(result, RankingResult)
        assert result.top_papers == []
        assert result.backbone_paths == []

    def test_invalid_alpha_raises(self):
        svc = _make_service({}, {}, {}, [0.0], [])
        with pytest.raises(ValueError, match="alpha"):
            svc.rank("q", _make_subgraph("p1"), alpha=-0.1)
        with pytest.raises(ValueError, match="alpha"):
            svc.rank("q", _make_subgraph("p1"), alpha=1.1)

    def test_invalid_top_k_raises(self):
        svc = _make_service({}, {}, {}, [0.0], [])
        with pytest.raises(ValueError, match="top_k"):
            svc.rank("q", _make_subgraph("p1"), top_k=0)

    def test_returns_ranking_result_type(self):
        q_vec = _unit_vector(2, 0)
        svc = _make_service(
            pr={"p1": 1.0, "p2": 0.5},
            bw={"p1": 0.0, "p2": 0.0},
            paper_embeddings={"p1": _unit_vector(2, 0), "p2": _unit_vector(2, 1)},
            query_vector=q_vec,
            edges=[],
        )
        result = svc.rank("q", _make_subgraph("p1", "p2"))
        assert isinstance(result, RankingResult)
        assert all(isinstance(sp, ScoredPaper) for sp in result.top_papers)

    def test_alpha_one_uses_only_centrality(self):
        # p2 has higher centrality; p1 has higher semantic.
        q_vec = _unit_vector(2, 0)
        svc = _make_service(
            pr={"p1": 0.0, "p2": 1.0},
            bw={"p1": 0.0, "p2": 0.0},
            paper_embeddings={"p1": _unit_vector(2, 0), "p2": _unit_vector(2, 1)},
            query_vector=q_vec,
            edges=[],
        )
        result = svc.rank("q", _make_subgraph("p1", "p2"), alpha=1.0)
        assert result.top_papers[0].paper.paper_id == "p2"

    def test_alpha_zero_uses_only_semantic(self):
        # p1 has perfect semantic match; p2 has higher centrality.
        q_vec = _unit_vector(2, 0)
        svc = _make_service(
            pr={"p1": 0.0, "p2": 1.0},
            bw={"p1": 0.0, "p2": 0.0},
            paper_embeddings={"p1": _unit_vector(2, 0), "p2": _unit_vector(2, 1)},
            query_vector=q_vec,
            edges=[],
        )
        result = svc.rank("q", _make_subgraph("p1", "p2"), alpha=0.0)
        assert result.top_papers[0].paper.paper_id == "p1"

    def test_combined_score_formula(self):
        from aievograph.domain.services.centrality_ranking_service import _DEFAULT_GAMMA
        # p1: pr=1.0, bw=0.0 → centrality_combined = _DEFAULT_GAMMA*1.0 + (1-_DEFAULT_GAMMA)*0.0
        #     semantic: orthogonal to query → 0.0
        #     combined (alpha=0.5): 0.5*centrality + 0.5*0.0
        # p2: pr=0.0, bw=0.0 → centrality_combined = 0.0
        #     semantic: same direction as query → normalized to 1.0
        #     combined (alpha=0.5): 0.5*0.0 + 0.5*1.0 = 0.5
        q_vec = _unit_vector(2, 0)
        svc = _make_service(
            pr={"p1": 1.0, "p2": 0.0},
            bw={"p1": 0.0, "p2": 0.0},
            paper_embeddings={"p1": _unit_vector(2, 1), "p2": _unit_vector(2, 0)},
            query_vector=q_vec,
            edges=[],
        )
        result = svc.rank("q", _make_subgraph("p1", "p2"), alpha=0.5)
        scores = {sp.paper.paper_id: sp.score for sp in result.top_papers}
        expected_p1 = 0.5 * _DEFAULT_GAMMA  # centrality=_DEFAULT_GAMMA, semantic=0
        assert scores["p1"] == pytest.approx(expected_p1)
        assert scores["p2"] == pytest.approx(0.5)    # centrality=0, semantic=1.0

    def test_top_k_limits_output(self):
        q_vec = [1.0, 0.0]
        ids = ["p1", "p2", "p3", "p4", "p5"]
        pr = {pid: float(i) for i, pid in enumerate(ids)}
        bw = {pid: 0.0 for pid in ids}
        embs = {pid: [1.0, 0.0] for pid in ids}
        svc = _make_service(pr=pr, bw=bw, paper_embeddings=embs, query_vector=q_vec, edges=[])
        result = svc.rank("q", _make_subgraph(*ids), top_k=3)
        assert len(result.top_papers) == 3

    def test_top_k_larger_than_papers_returns_all(self):
        q_vec = [1.0, 0.0]
        svc = _make_service(
            pr={"p1": 1.0, "p2": 0.5},
            bw={"p1": 0.0, "p2": 0.0},
            paper_embeddings={"p1": [1.0, 0.0], "p2": [1.0, 0.0]},
            query_vector=q_vec,
            edges=[],
        )
        result = svc.rank("q", _make_subgraph("p1", "p2"), top_k=100)
        assert len(result.top_papers) == 2

    def test_tiebreaker_is_paper_id_ascending(self):
        # Both papers get identical combined score.
        q_vec = [1.0, 0.0]
        svc = _make_service(
            pr={"p_b": 1.0, "p_a": 1.0},
            bw={"p_b": 0.0, "p_a": 0.0},
            paper_embeddings={"p_b": [1.0, 0.0], "p_a": [1.0, 0.0]},
            query_vector=q_vec,
            edges=[],
        )
        result = svc.rank("q", _make_subgraph("p_b", "p_a"), alpha=0.5)
        assert result.top_papers[0].paper.paper_id == "p_a"

    def test_backbone_paths_included_in_result(self):
        # p2 cites p1 → backbone path [p1, p2]
        q_vec = [1.0, 0.0]
        svc = _make_service(
            pr={"p1": 1.0, "p2": 0.5},
            bw={"p1": 0.0, "p2": 0.0},
            paper_embeddings={"p1": [1.0, 0.0], "p2": [1.0, 0.0]},
            query_vector=q_vec,
            edges=[("p2", "p1")],
        )
        result = svc.rank("q", _make_subgraph("p1", "p2"))
        assert ["p1", "p2"] in result.backbone_paths

    def test_backbone_only_within_top_k(self):
        # p3 is outside top-1; its citation edge should not appear in backbone.
        q_vec = [1.0, 0.0]
        svc = _make_service(
            pr={"p1": 1.0, "p2": 0.5, "p3": 0.1},
            bw={"p1": 0.0, "p2": 0.0, "p3": 0.0},
            paper_embeddings={
                "p1": [1.0, 0.0], "p2": [1.0, 0.0], "p3": [1.0, 0.0]
            },
            query_vector=q_vec,
            edges=[("p3", "p2"), ("p2", "p1")],
        )
        result = svc.rank("q", _make_subgraph("p1", "p2", "p3"), top_k=1)
        # Only p1 is in top-1; no edges, no backbone.
        assert result.backbone_paths == []


# ---------------------------------------------------------------------------
# Integration test: Subgraph → full Ranking pipeline (Layer C, Step 4.3)
# ---------------------------------------------------------------------------

class TestRankingPipelineIntegration:
    """End-to-end test: Subgraph → CombinedRankingService → RankingResult.

    Exercises all three pipeline stages (centrality, semantic, backbone) together
    using only in-process stubs — no external dependencies.
    """

    def test_full_pipeline_returns_correct_top_papers_and_backbone(self):
        # Setup: three papers in a citation chain p1 ← p2 ← p3.
        # p3 has the highest centrality (it cites both); p1 matches the query best.
        # alpha=0.5 so combined score balances both signals.
        q_vec = _unit_vector(3, 0)   # query aligns with p1's embedding
        svc = _make_service(
            pr={"p1": 0.0, "p2": 0.5, "p3": 1.0},
            bw={"p1": 0.0, "p2": 0.0, "p3": 0.0},
            paper_embeddings={
                "p1": _unit_vector(3, 0),  # cosine sim = 1.0 with query
                "p2": _unit_vector(3, 1),  # cosine sim = 0.0 with query
                "p3": _unit_vector(3, 2),  # cosine sim = 0.0 with query
            },
            query_vector=q_vec,
            edges=[("p2", "p1"), ("p3", "p2")],  # p1 oldest, p3 newest
        )
        result = svc.rank("query about p1", _make_subgraph("p1", "p2", "p3"), top_k=3)

        # All three papers must appear in top_papers.
        top_ids = [sp.paper.paper_id for sp in result.top_papers]
        assert set(top_ids) == {"p1", "p2", "p3"}

        # Scores must be non-negative.
        assert all(sp.score >= 0.0 for sp in result.top_papers)

        # Backbone must include the full lineage path p1 → p2 → p3.
        assert ["p1", "p2", "p3"] in result.backbone_paths
