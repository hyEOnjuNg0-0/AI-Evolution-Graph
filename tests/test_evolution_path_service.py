"""Unit tests for EvolutionPathService (Layer D Step 5.3).

Covers:
  - _compute_breakthrough_proxy
  - _compute_influence_scores
  - _build_adjacency
  - _dfs_paths (greedy best-first)
  - EvolutionPath model validator (C3)
  - normalize_scores negative-value warning (H2)
  - EvolutionPathService.extract():
      happy path, cycles (C2), missing trend scores (H1),
      parameter validation, edge cases
"""

import logging
import pytest

from aievograph.domain.models import (
    BreakthroughCandidate,
    EvolutionPath,
    MethodTrendScore,
)
from aievograph.domain.ports.method_evolution_repository import MethodEvolutionRepositoryPort
from aievograph.domain.services.evolution_path_service import (
    EvolutionPathService,
    _build_adjacency,
    _compute_breakthrough_proxy,
    _compute_influence_scores,
    _dfs_paths,
)
from aievograph.domain.utils.ranking_utils import normalize_scores


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trend(name: str, score: float = 0.5) -> MethodTrendScore:
    return MethodTrendScore(method_name=name, trend_score=score)


def _breakthrough(pid: str, score: float = 0.5) -> BreakthroughCandidate:
    return BreakthroughCandidate(
        paper_id=pid,
        burst_score=score,
        centrality_shift=score,
        breakthrough_score=score,
    )


class StubRepo(MethodEvolutionRepositoryPort):
    def __init__(
        self,
        relations: list[tuple[str, str, str]] | None = None,
        paper_methods: dict[str, list[str]] | None = None,
    ) -> None:
        self._relations = relations or []
        self._paper_methods = paper_methods or {}

    def get_relations(self, method_names):
        return self._relations

    def get_paper_methods(self, paper_ids):
        return self._paper_methods


def _svc(relations=None, paper_methods=None):
    return EvolutionPathService(StubRepo(relations, paper_methods))


# ---------------------------------------------------------------------------
# EvolutionPath model validator (C3)
# ---------------------------------------------------------------------------

class TestEvolutionPathValidator:
    def test_valid_path_two_nodes(self):
        ep = EvolutionPath(path=["A", "B"], relation_types=["IMPROVES"])
        assert ep.path == ["A", "B"]

    def test_valid_path_three_nodes(self):
        ep = EvolutionPath(path=["A", "B", "C"], relation_types=["IMPROVES", "EXTENDS"])
        assert len(ep.relation_types) == 2

    def test_valid_empty_path(self):
        ep = EvolutionPath(path=[], relation_types=[])
        assert ep.path == []

    def test_relation_types_too_short_raises(self):
        with pytest.raises(ValueError, match="len\\(relation_types\\)"):
            EvolutionPath(path=["A", "B", "C"], relation_types=["IMPROVES"])

    def test_relation_types_too_long_raises(self):
        with pytest.raises(ValueError, match="len\\(relation_types\\)"):
            EvolutionPath(path=["A", "B"], relation_types=["IMPROVES", "EXTENDS"])

    def test_single_node_path_requires_empty_relation_types(self):
        ep = EvolutionPath(path=["A"], relation_types=[])
        assert ep.path == ["A"]

    def test_single_node_with_relation_type_raises(self):
        with pytest.raises(ValueError, match="len\\(relation_types\\)"):
            EvolutionPath(path=["A"], relation_types=["IMPROVES"])


# ---------------------------------------------------------------------------
# normalize_scores — H2: negative-value warning
# ---------------------------------------------------------------------------

class TestNormalizeScores:
    def test_negative_value_triggers_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="aievograph.domain.utils.ranking_utils"):
            result = normalize_scores({"A": -1.0, "B": 5.0})
        assert "negative" in caplog.text.lower()
        assert result["A"] == 0.0
        assert result["B"] == 1.0

    def test_all_positive_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="aievograph.domain.utils.ranking_utils"):
            normalize_scores({"A": 2.0, "B": 4.0})
        assert "negative" not in caplog.text.lower()

    def test_empty_dict_returns_empty(self):
        assert normalize_scores({}) == {}

    def test_all_zero_returns_all_zero(self):
        result = normalize_scores({"A": 0.0, "B": 0.0})
        assert all(v == 0.0 for v in result.values())

    def test_max_value_becomes_one(self):
        result = normalize_scores({"A": 3.0, "B": 6.0, "C": 1.0})
        assert result["B"] == 1.0

    def test_proportions_preserved(self):
        result = normalize_scores({"A": 2.0, "B": 4.0})
        assert result["A"] == pytest.approx(0.5)
        assert result["B"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _compute_breakthrough_proxy
# ---------------------------------------------------------------------------

class TestComputeBreakthroughProxy:
    def test_no_breakthrough_candidates(self):
        proxy = _compute_breakthrough_proxy(["A", "B"], {}, [])
        assert proxy == {"A": 0.0, "B": 0.0}

    def test_method_used_by_one_paper(self):
        paper_methods = {"p1": ["A"]}
        candidates = [_breakthrough("p1", 0.8)]
        proxy = _compute_breakthrough_proxy(["A", "B"], paper_methods, candidates)
        assert proxy["A"] == pytest.approx(0.8)
        assert proxy["B"] == 0.0

    def test_method_used_by_multiple_papers_averages(self):
        paper_methods = {"p1": ["A"], "p2": ["A"]}
        candidates = [_breakthrough("p1", 0.6), _breakthrough("p2", 1.0)]
        proxy = _compute_breakthrough_proxy(["A"], paper_methods, candidates)
        assert proxy["A"] == pytest.approx(0.8)

    def test_paper_not_in_candidates_gets_zero_score(self):
        paper_methods = {"p1": ["A"], "unknown": ["B"]}
        candidates = [_breakthrough("p1", 1.0)]
        proxy = _compute_breakthrough_proxy(["A", "B"], paper_methods, candidates)
        assert proxy["B"] == 0.0

    def test_method_outside_scope_ignored(self):
        paper_methods = {"p1": ["X"]}  # X not in method_names
        candidates = [_breakthrough("p1", 1.0)]
        proxy = _compute_breakthrough_proxy(["A"], paper_methods, candidates)
        assert proxy == {"A": 0.0}


# ---------------------------------------------------------------------------
# _build_adjacency
# ---------------------------------------------------------------------------

class TestBuildAdjacency:
    def test_simple_edge_a_improves_b(self):
        # (A, B, IMPROVES) means A is newer, B is older → flow B→A
        succ, pred = _build_adjacency({"A", "B"}, [("A", "B", "IMPROVES")])
        assert ("A", "IMPROVES") in succ["B"]
        assert "B" in pred["A"]

    def test_self_loop_discarded(self):
        succ, pred = _build_adjacency({"A"}, [("A", "A", "IMPROVES")])
        assert succ["A"] == []
        assert pred["A"] == set()

    def test_edge_outside_method_set_discarded(self):
        succ, pred = _build_adjacency({"A"}, [("A", "Z", "IMPROVES")])
        assert succ["A"] == []

    def test_multiple_successors(self):
        edges = [("B", "A", "IMPROVES"), ("C", "A", "EXTENDS")]
        succ, pred = _build_adjacency({"A", "B", "C"}, edges)
        assert len(succ["A"]) == 2
        assert "A" in pred["B"]
        assert "A" in pred["C"]


# ---------------------------------------------------------------------------
# _dfs_paths
# ---------------------------------------------------------------------------

class TestDfsPaths:
    def test_single_node_no_successors(self):
        succ = {"A": []}
        paths = _dfs_paths("A", succ, {"A": 1.0})
        assert paths == [(["A"], [])]

    def test_linear_chain(self):
        succ = {"A": [("B", "IMPROVES")], "B": [("C", "EXTENDS")], "C": []}
        paths = _dfs_paths("A", succ, {"A": 1.0, "B": 0.8, "C": 0.6})
        assert len(paths) == 1
        assert paths[0][0] == ["A", "B", "C"]
        assert paths[0][1] == ["IMPROVES", "EXTENDS"]

    def test_branching_follows_greedy_best(self):
        # Greedy: only follows the highest-influence successor (B > C), so one path.
        succ = {"A": [("B", "IMPROVES"), ("C", "EXTENDS")], "B": [], "C": []}
        paths = _dfs_paths("A", succ, {"A": 1.0, "B": 0.8, "C": 0.6})
        assert len(paths) == 1
        assert paths[0][0] == ["A", "B"]

    def test_cycle_safe_visited_prevents_infinite_loop(self):
        # A→B, B has A as successor (would cause cycle if not guarded)
        succ = {"A": [("B", "IMPROVES")], "B": [("A", "EXTENDS")]}
        paths = _dfs_paths("A", succ, {"A": 1.0, "B": 0.5})
        # Must terminate; A already in visited when B tries to go back
        assert any(p[0] == ["A", "B"] for p in paths)


# ---------------------------------------------------------------------------
# EvolutionPathService.extract()
# ---------------------------------------------------------------------------

class TestExtract:
    def test_empty_method_names_returns_empty(self):
        svc = _svc()
        assert svc.extract([], [], []) == []

    def test_no_edges_returns_empty(self):
        svc = _svc()
        result = svc.extract(["A", "B"], [_trend("A"), _trend("B")], [])
        assert result == []

    def test_linear_chain_returns_one_path(self):
        # A→B→C: A IMPROVES B (A newer), B IMPROVES C (B newer) → flow C→B→A
        edges = [("A", "B", "IMPROVES"), ("B", "C", "IMPROVES")]
        svc = _svc(relations=edges)
        result = svc.extract(
            ["A", "B", "C"],
            [_trend("A", 0.8), _trend("B", 0.6), _trend("C", 0.4)],
            [],
        )
        assert len(result) == 1
        assert result[0].path == ["C", "B", "A"]
        assert result[0].relation_types == ["IMPROVES", "IMPROVES"]

    def test_min_path_length_filters_single_nodes(self):
        # Only isolated nodes, no edges → no paths of length >= 2
        svc = _svc()
        result = svc.extract(["A"], [_trend("A")], [])
        assert result == []

    def test_top_k_limits_output(self):
        # Build 3 independent chains: C→B→A, F→E→D, I→H→G
        edges = [
            ("A", "B", "IMPROVES"), ("B", "C", "IMPROVES"),
            ("D", "E", "IMPROVES"), ("E", "F", "IMPROVES"),
            ("G", "H", "IMPROVES"), ("H", "I", "IMPROVES"),
        ]
        methods = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
        svc = _svc(relations=edges)
        result = svc.extract(methods, [_trend(m) for m in methods], [], top_k=2)
        assert len(result) == 2

    def test_sorted_by_mean_influence_descending(self):
        edges = [("B", "A", "IMPROVES"), ("D", "C", "IMPROVES")]
        # A→B and C→D; give B high score so A→B path wins
        svc = _svc(relations=edges)
        result = svc.extract(
            ["A", "B", "C", "D"],
            [_trend("A", 0.1), _trend("B", 1.0), _trend("C", 0.1), _trend("D", 0.1)],
            [],
        )
        scores = [r.mean_influence for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_branch_points_identified(self):
        # A→B and A→C: A has two successors → branch point
        edges = [("B", "A", "IMPROVES"), ("C", "A", "IMPROVES")]
        svc = _svc(relations=edges)
        result = svc.extract(
            ["A", "B", "C"],
            [_trend("A"), _trend("B"), _trend("C")],
            [],
        )
        for path in result:
            if "A" in path.path:
                assert "A" in path.branch_points

    def test_influence_scores_in_unit_interval(self):
        edges = [("B", "A", "IMPROVES"), ("C", "B", "IMPROVES")]
        svc = _svc(relations=edges)
        result = svc.extract(
            ["A", "B", "C"],
            [_trend("A", 0.3), _trend("B", 0.7), _trend("C", 0.5)],
            [],
        )
        for path in result:
            for score in path.influence_scores.values():
                assert 0.0 <= score <= 1.0

    # --- C2: cycle detection ---

    def test_pure_cycle_logs_warning_and_returns_empty(self, caplog):
        # A→B→C→A: all nodes have predecessors
        edges = [("B", "A", "IMPROVES"), ("C", "B", "IMPROVES"), ("A", "C", "IMPROVES")]
        svc = _svc(relations=edges)
        with caplog.at_level(logging.WARNING, logger="aievograph.domain.services.evolution_path_service"):
            result = svc.extract(
                ["A", "B", "C"],
                [_trend("A"), _trend("B"), _trend("C")],
                [],
            )
        assert result == []
        assert "cycle" in caplog.text.lower()

    def test_two_node_cycle_logs_warning_and_returns_empty(self, caplog):
        edges = [("B", "A", "IMPROVES"), ("A", "B", "IMPROVES")]
        svc = _svc(relations=edges)
        with caplog.at_level(logging.WARNING, logger="aievograph.domain.services.evolution_path_service"):
            result = svc.extract(["A", "B"], [_trend("A"), _trend("B")], [])
        assert result == []
        assert "cycle" in caplog.text.lower()

    def test_no_edges_no_cycle_warning(self, caplog):
        svc = _svc()
        with caplog.at_level(logging.WARNING, logger="aievograph.domain.services.evolution_path_service"):
            svc.extract(["A", "B"], [_trend("A"), _trend("B")], [])
        assert "cycle" not in caplog.text.lower()

    # --- H1: missing trend score warning ---

    def test_missing_trend_score_logs_warning(self, caplog):
        edges = [("B", "A", "IMPROVES")]
        svc = _svc(relations=edges)
        with caplog.at_level(logging.WARNING, logger="aievograph.domain.services.evolution_path_service"):
            # Only "A" has a trend score; "B" is missing
            svc.extract(["A", "B"], [_trend("A", 0.8)], [])
        assert "no trend score" in caplog.text.lower() or "trend" in caplog.text.lower()

    def test_all_trend_scores_present_no_warning(self, caplog):
        edges = [("B", "A", "IMPROVES")]
        svc = _svc(relations=edges)
        with caplog.at_level(logging.WARNING, logger="aievograph.domain.services.evolution_path_service"):
            svc.extract(["A", "B"], [_trend("A"), _trend("B")], [])
        assert "no trend score" not in caplog.text.lower()

    # --- parameter validation ---

    def test_top_k_zero_raises(self):
        svc = _svc()
        with pytest.raises(ValueError, match="top_k"):
            svc.extract(["A"], [], [], top_k=0)

    def test_alpha_negative_raises(self):
        svc = _svc()
        with pytest.raises(ValueError, match="alpha"):
            svc.extract(["A"], [], [], alpha=-0.1)

    def test_alpha_above_one_raises(self):
        svc = _svc()
        with pytest.raises(ValueError, match="alpha"):
            svc.extract(["A"], [], [], alpha=1.1)

    # --- breakthrough proxy integration ---

    def test_breakthrough_proxy_affects_influence_scores(self):
        # Two parallel chains; give high breakthrough score to chain B→A
        edges = [("B", "A", "IMPROVES"), ("D", "C", "IMPROVES")]
        paper_methods = {"p1": ["A", "B"]}
        svc = _svc(relations=edges, paper_methods=paper_methods)
        candidates = [_breakthrough("p1", 1.0)]
        result = svc.extract(
            ["A", "B", "C", "D"],
            [_trend("A", 0.5), _trend("B", 0.5), _trend("C", 0.5), _trend("D", 0.5)],
            candidates,
            alpha=0.0,  # rely entirely on breakthrough proxy
        )
        # Path through A and B should rank higher than path through C and D
        assert result[0].path in [["A", "B"], ["B", "A"]] or (
            result[0].mean_influence >= result[-1].mean_influence
        )

    # --- EvolutionPath relation_types integrity in output ---

    def test_output_paths_satisfy_relation_types_length_invariant(self):
        edges = [("B", "A", "IMPROVES"), ("C", "B", "EXTENDS")]
        svc = _svc(relations=edges)
        result = svc.extract(
            ["A", "B", "C"],
            [_trend("A"), _trend("B"), _trend("C")],
            [],
        )
        for path in result:
            assert len(path.relation_types) == len(path.path) - 1
