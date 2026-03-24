"""
CentralityRankingService + EmbeddingRankingService + SubgraphEdgeRepositoryPort
        ↓
CombinedRankingService  (Layer C — Hybrid Ranking & Graph Pruning, Step 4.3)
        ↓
  rank(query, subgraph, alpha, top_k) → RankingResult

Pipeline:
  [1] CentralityRankingService.score_breakdown(subgraph)
      → per-paper centrality scores (already normalized to [0, 1])
  [2] EmbeddingRankingService.rank(query, subgraph)
      → per-paper semantic similarity scores (already normalized to [0, 1])
  [3] Combined score = alpha × centrality + (1 − alpha) × semantic
  [4] Sort descending, select top-k → top_papers
  [5] SubgraphEdgeRepositoryPort.get_citation_edges(top_k_ids)
      → citation edges within top-k papers
  [6] Backbone extraction: longest paths in citation DAG (oldest → newest)
  [7] Return RankingResult(top_papers, backbone_paths)
"""

import logging

from aievograph.domain.models import RankingResult, ScoredPaper, Subgraph
from aievograph.domain.ports.subgraph_edge_repository import SubgraphEdgeRepositoryPort
from aievograph.domain.services.centrality_ranking_service import CentralityRankingService
from aievograph.domain.services.embedding_ranking_service import EmbeddingRankingService

logger = logging.getLogger(__name__)

_DEFAULT_ALPHA = 0.5  # weight for centrality score; (1 − alpha) goes to semantic
_DEFAULT_TOP_K = 10
_MIN_BACKBONE_LENGTH = 2  # discard single-node paths


def _extract_backbone_paths(
    paper_ids: set[str],
    edges: list[tuple[str, str]],
    scores: dict[str, float],
) -> list[list[str]]:
    """Extract maximal research-lineage paths from the citation DAG.

    Direction: cited → citing (oldest paper first = research flow direction).
    Cycle-safe: visited set is tracked per DFS traversal.
    Only paths of length >= _MIN_BACKBONE_LENGTH are kept.
    Result is sorted by mean combined score descending.

    Args:
        paper_ids: IDs of papers that form the subgraph nodes.
        edges: (citing_paper_id, cited_paper_id) pairs within paper_ids.
        scores: Combined score per paper_id for path ranking.

    Returns:
        List of paper_id paths, each ordered oldest → newest.
    """
    # Build "research flow" adjacency: cited → citing (old → new).
    successors: dict[str, list[str]] = {pid: [] for pid in paper_ids}
    predecessors: dict[str, set[str]] = {pid: set() for pid in paper_ids}

    for citing, cited in edges:
        if citing in paper_ids and cited in paper_ids and citing != cited:
            successors[cited].append(citing)
            predecessors[citing].add(cited)

    # Prefer high-scoring successors first (greedy DFS order).
    for pid in successors:
        successors[pid].sort(key=lambda x: -scores.get(x, 0.0))

    # Source nodes have no predecessors in this subgraph (oldest papers).
    # Sort deterministically so that equal-score paths always appear in the same order.
    sources = sorted(pid for pid in paper_ids if not predecessors[pid])

    paths: list[list[str]] = []

    def _dfs(node: str, path: list[str], visited: set[str]) -> None:
        next_nodes = [s for s in successors[node] if s not in visited]
        if not next_nodes:
            # Leaf node — record path if long enough.
            if len(path) >= _MIN_BACKBONE_LENGTH:
                paths.append(list(path))
            return
        for nxt in next_nodes:
            path.append(nxt)
            visited.add(nxt)
            _dfs(nxt, path, visited)
            path.pop()
            visited.discard(nxt)

    for src in sources:
        _dfs(src, [src], {src})

    # Sort by mean score descending; use path itself as lexicographic tiebreaker
    # so equal-score paths always appear in a deterministic order.
    paths.sort(
        key=lambda p: (-(sum(scores.get(pid, 0.0) for pid in p) / len(p)), p)
    )
    return paths


class CombinedRankingService:
    """Combine centrality and semantic scores, then extract backbone paths (Layer C Step 4.3)."""

    def __init__(
        self,
        centrality_svc: CentralityRankingService,
        embedding_svc: EmbeddingRankingService,
        edge_repo: SubgraphEdgeRepositoryPort,
    ) -> None:
        self._centrality_svc = centrality_svc
        self._embedding_svc = embedding_svc
        self._edge_repo = edge_repo

    def rank(
        self,
        query: str,
        subgraph: Subgraph,
        alpha: float = _DEFAULT_ALPHA,
        top_k: int = _DEFAULT_TOP_K,
    ) -> RankingResult:
        """Produce top-k papers and backbone paths from the input subgraph.

        Args:
            query: Natural-language query text (used for semantic scoring).
            subgraph: Candidate papers from Layer B hybrid retrieval.
            alpha: Weight for centrality in [0, 1]; (1 − alpha) goes to semantic.
            top_k: Maximum number of papers to include in top_papers.

        Returns:
            RankingResult with top_papers sorted by combined score descending
            and backbone_paths extracted from the top-k citation subgraph.

        Raises:
            ValueError: If alpha is outside [0.0, 1.0] or top_k < 1.
        """
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"alpha must be in [0.0, 1.0], got {alpha}")
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")
        if not subgraph.papers:
            return RankingResult()

        # [1] Centrality scores (normalized combined_score per paper).
        centrality_breakdown = self._centrality_svc.score_breakdown(subgraph)
        centrality_map: dict[str, float] = {
            c.paper_id: c.combined_score for c in centrality_breakdown
        }

        # [2] Semantic similarity scores (normalized per paper).
        semantic_results = self._embedding_svc.rank(query, subgraph)
        semantic_map: dict[str, float] = {
            sp.paper.paper_id: sp.score for sp in semantic_results
        }

        # [3] Combined score = alpha × centrality + (1 − alpha) × semantic.
        papers_map = {sp.paper.paper_id: sp.paper for sp in subgraph.papers}
        scored: list[ScoredPaper] = [
            ScoredPaper(
                paper=papers_map[pid],
                score=(
                    alpha * centrality_map.get(pid, 0.0)
                    + (1.0 - alpha) * semantic_map.get(pid, 0.0)
                ),
            )
            for pid in papers_map
        ]

        # [4] Sort descending, then paper_id as tiebreaker; select top-k.
        scored.sort(key=lambda sp: (-sp.score, sp.paper.paper_id))
        top_papers = scored[:top_k]

        # [5] Fetch citation edges within top-k paper set.
        top_ids = [sp.paper.paper_id for sp in top_papers]
        edges = self._edge_repo.get_citation_edges(top_ids)

        # [6] Extract backbone paths.
        scores_for_backbone = {sp.paper.paper_id: sp.score for sp in top_papers}
        backbone_paths = _extract_backbone_paths(
            paper_ids=set(top_ids),
            edges=edges,
            scores=scores_for_backbone,
        )

        logger.debug(
            "Combined ranking: %d papers → top-%d, %d backbone paths",
            len(subgraph.papers),
            len(top_papers),
            len(backbone_paths),
        )
        return RankingResult(top_papers=top_papers, backbone_paths=backbone_paths)
