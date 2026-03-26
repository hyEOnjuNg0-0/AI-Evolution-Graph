"""
MethodEvolutionRepositoryPort + list[MethodTrendScore] + list[BreakthroughCandidate]
        ↓
EvolutionPathService  (Layer D — Evolution Path 생성, Step 5.3)
        ↓
  extract(method_names, trend_scores, breakthrough_candidates, ...) → list[EvolutionPath]

Pipeline:
  [1] MethodEvolutionRepositoryPort.get_paper_methods(breakthrough_paper_ids)
      → paper_id → [method_names]  (maps breakthrough signal from papers to methods)
  [2] Compute per-method breakthrough proxy:
        proxy[m] = mean(breakthrough_score for papers that use method m)
  [3] Influence score = alpha × trend_score + (1 − alpha) × breakthrough_proxy
      → max-normalize to [0, 1]
  [4] MethodEvolutionRepositoryPort.get_relations(method_names)
      → (source, target, relation_type) edges  (source IMPROVES/EXTENDS/REPLACES target)
  [5] Build research-flow adjacency: target → source  (old → new)
  [6] DFS from source nodes (no predecessors) → extract all maximal paths (len ≥ 2)
  [7] Identify branch points: methods with ≥ 2 successors in the subgraph
  [8] Score paths by mean influence; sort descending; return top_k

Edge direction convention (Neo4j schema):
  (src:Method)-[:IMPROVES]->(tgt:Method)
  means src is the NEWER method that improves the OLDER tgt.
  Research flow = tgt → src  (oldest first).
"""

import logging

from aievograph.domain.models import (
    BreakthroughCandidate,
    EvolutionPath,
    MethodTrendScore,
)
from aievograph.domain.ports.method_evolution_repository import MethodEvolutionRepositoryPort
from aievograph.domain.utils.ranking_utils import normalize_scores

logger = logging.getLogger(__name__)

_DEFAULT_ALPHA = 0.5      # weight for trend_score vs breakthrough proxy
_DEFAULT_TOP_K = 10
_MIN_PATH_LENGTH = 2      # discard single-node paths


# ---------------------------------------------------------------------------
# Influence score helpers
# ---------------------------------------------------------------------------

def _compute_breakthrough_proxy(
    method_names: list[str],
    paper_methods: dict[str, list[str]],
    breakthrough_candidates: list[BreakthroughCandidate],
) -> dict[str, float]:
    """Compute per-method breakthrough proxy as mean paper breakthrough score.

    For each method, collects the breakthrough_scores of all papers that use it,
    then averages them.  Methods not used by any breakthrough paper receive 0.0.

    Args:
        method_names: Canonical method names in scope.
        paper_methods: {paper_id: [method_names]} from the repository.
        breakthrough_candidates: BreakthroughCandidate list from Step 5.1.

    Returns:
        Dict mapping method_name → raw breakthrough proxy (un-normalized).
    """
    method_scores: dict[str, list[float]] = {m: [] for m in method_names}
    score_map = {c.paper_id: c.breakthrough_score for c in breakthrough_candidates}

    for paper_id, methods in paper_methods.items():
        score = score_map.get(paper_id, 0.0)
        for m in methods:
            if m in method_scores:
                method_scores[m].append(score)

    return {
        m: (sum(scores) / len(scores) if scores else 0.0)
        for m, scores in method_scores.items()
    }


def _compute_influence_scores(
    method_names: list[str],
    trend_map: dict[str, float],
    breakthrough_proxy: dict[str, float],
    alpha: float,
) -> dict[str, float]:
    """Combine trend and breakthrough proxy into a single normalized influence score.

    Args:
        method_names: Methods to score.
        trend_map: method_name → normalized trend_score (from TrendMomentumService).
        breakthrough_proxy: method_name → raw breakthrough proxy.
        alpha: Weight for trend_score; (1 − alpha) goes to breakthrough proxy.

    Returns:
        Max-normalized influence scores in [0, 1].
    """
    # Normalize breakthrough proxy independently before blending.
    norm_proxy = normalize_scores(breakthrough_proxy)

    raw: dict[str, float] = {
        m: alpha * trend_map.get(m, 0.0) + (1.0 - alpha) * norm_proxy.get(m, 0.0)
        for m in method_names
    }
    return normalize_scores(raw)


# ---------------------------------------------------------------------------
# Path extraction helpers
# ---------------------------------------------------------------------------

def _build_adjacency(
    method_names: set[str],
    edges: list[tuple[str, str, str]],
) -> tuple[
    dict[str, list[tuple[str, str]]],  # research-flow successors: old → [(new, rel_type)]
    dict[str, set[str]],               # predecessors: new → {old, ...}
]:
    """Build directed research-flow adjacency lists from raw edge triples.

    Edge (src, tgt, rel_type) means src IMPROVES/EXTENDS/REPLACES tgt:
    tgt is OLDER, src is NEWER.  Research flow = tgt → src.

    Self-loops and edges outside method_names are discarded.
    """
    successors: dict[str, list[tuple[str, str]]] = {m: [] for m in method_names}
    predecessors: dict[str, set[str]] = {m: set() for m in method_names}

    for src, tgt, rel_type in edges:
        if src in method_names and tgt in method_names and src != tgt:
            successors[tgt].append((src, rel_type))
            predecessors[src].add(tgt)

    return successors, predecessors


def _dfs_paths(
    source: str,
    successors: dict[str, list[tuple[str, str]]],
    influence_scores: dict[str, float],
) -> list[tuple[list[str], list[str]]]:
    """Enumerate all maximal paths starting from source via DFS.

    Successors are visited in descending influence-score order (greedy).
    Cycle-safe: visited set is tracked per traversal.

    Returns:
        List of (path, relation_types) pairs; each path has length >= 1.
        Paths shorter than _MIN_PATH_LENGTH are filtered by the caller.
    """
    results: list[tuple[list[str], list[str]]] = []

    # Sort successors by influence score descending for greedy traversal order.
    for node in successors:
        successors[node].sort(key=lambda x: -influence_scores.get(x[0], 0.0))

    def _dfs(node: str, path: list[str], rels: list[str], visited: set[str]) -> None:
        next_nodes = [(s, r) for s, r in successors[node] if s not in visited]
        if not next_nodes:
            results.append((list(path), list(rels)))
            return
        for nxt, rel in next_nodes:
            path.append(nxt)
            rels.append(rel)
            visited.add(nxt)
            _dfs(nxt, path, rels, visited)
            path.pop()
            rels.pop()
            visited.discard(nxt)

    _dfs(source, [source], [], {source})
    return results


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class EvolutionPathService:
    """Extract evolution paths from the Method Evolution Graph (Layer D Step 5.3)."""

    def __init__(self, repo: MethodEvolutionRepositoryPort) -> None:
        self._repo = repo

    def extract(
        self,
        method_names: list[str],
        trend_scores: list[MethodTrendScore],
        breakthrough_candidates: list[BreakthroughCandidate],
        top_k: int = _DEFAULT_TOP_K,
        alpha: float = _DEFAULT_ALPHA,
    ) -> list[EvolutionPath]:
        """Extract and rank evolution paths from the Method Evolution Graph.

        Args:
            method_names: Canonical method names to include in the subgraph.
            trend_scores: Per-method trend momentum scores from Step 5.2.
            breakthrough_candidates: Per-paper breakthrough signals from Step 5.1.
                Used to compute a per-method breakthrough proxy via paper→method mapping.
            top_k: Maximum number of evolution paths to return.
            alpha: Weight for trend_score in influence computation; (1-alpha) goes to
                   breakthrough proxy.

        Returns:
            List of EvolutionPaths sorted by mean_influence descending.
            Paths shorter than 2 methods are excluded.

        Raises:
            ValueError: If top_k < 1 or alpha outside [0.0, 1.0].
        """
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"alpha must be in [0.0, 1.0], got {alpha}")
        if not method_names:
            return []

        method_set = set(method_names)
        trend_map = {ts.method_name: ts.trend_score for ts in trend_scores}

        # H1: warn on methods with no trend score — they default to 0.0, which can distort ranking.
        missing_trend = [m for m in method_names if m not in trend_map]
        if missing_trend:
            logger.warning(
                "Evolution path: %d method(s) have no trend score and will default to 0.0: %s%s",
                len(missing_trend),
                missing_trend[:5],
                " …" if len(missing_trend) > 5 else "",
            )

        # [1] Map breakthrough signal from papers to methods.
        paper_ids = [c.paper_id for c in breakthrough_candidates]
        paper_methods = self._repo.get_paper_methods(paper_ids) if paper_ids else {}

        # [2] Compute per-method breakthrough proxy.
        breakthrough_proxy = _compute_breakthrough_proxy(
            method_names, paper_methods, breakthrough_candidates
        )

        # [3] Compute influence scores (trend + breakthrough, normalized).
        influence_scores = _compute_influence_scores(
            method_names, trend_map, breakthrough_proxy, alpha
        )

        # [4] Fetch method-relation edges within the subgraph.
        edges = self._repo.get_relations(method_names)

        # [5] Build research-flow adjacency.
        successors, predecessors = _build_adjacency(method_set, edges)

        # [6] Identify branch points (out-degree >= 2 in research-flow graph).
        branch_point_set = {m for m in method_names if len(successors[m]) >= 2}

        # [7] DFS from source nodes (no predecessors = oldest methods).
        sources = sorted(m for m in method_names if not predecessors[m])

        # C2: if there are edges but no sources, all nodes are in cycles — warn explicitly.
        if not sources and edges:
            logger.warning(
                "Evolution path extraction: all %d methods form cycles — no DAG source nodes found. "
                "Returning empty results. Check for cyclic IMPROVES/EXTENDS/REPLACES relations.",
                len(method_names),
            )
            return []

        raw_paths: list[tuple[list[str], list[str]]] = []
        for src in sources:
            raw_paths.extend(_dfs_paths(src, successors, influence_scores))

        # [8] Build EvolutionPath objects, filter short paths, sort, return top_k.
        results: list[EvolutionPath] = []
        for path, rel_types in raw_paths:
            if len(path) < _MIN_PATH_LENGTH:
                continue
            scores = {m: influence_scores.get(m, 0.0) for m in path}
            mean_inf = sum(scores.values()) / len(scores)
            results.append(
                EvolutionPath(
                    path=path,
                    relation_types=rel_types,
                    branch_points=[m for m in path if m in branch_point_set],
                    influence_scores=scores,
                    mean_influence=mean_inf,
                )
            )

        results.sort(key=lambda p: (-p.mean_influence, p.path))

        logger.debug(
            "Evolution path extraction: %d methods, %d edges → %d paths, returning top-%d",
            len(method_names),
            len(edges),
            len(results),
            min(top_k, len(results)),
        )
        return results[:top_k]
