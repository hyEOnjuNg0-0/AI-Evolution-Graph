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
from aievograph.domain.utils.graph_utils import extract_dag_paths
from aievograph.domain.utils.ranking_utils import build_papers_map, sort_scored_papers
from aievograph.domain.utils.validation_utils import validate_positive_int, validate_unit_weights

logger = logging.getLogger(__name__)

_DEFAULT_ALPHA = 0.5  # weight for centrality score; (1 − alpha) goes to semantic
_DEFAULT_TOP_K = 10
_MIN_BACKBONE_LENGTH = 2  # discard single-node paths


def _extract_backbone_paths(
    paper_ids: set[str],
    edges: list[tuple[str, str]],
    scores: dict[str, float],
) -> list[list[str]]:
    """Extract backbone paths from citation DAG (oldest → newest = research flow).

    Thin wrapper around extract_dag_paths that converts citation edges
    (citing, cited) to research-flow direction (cited → citing) before extraction.

    Args:
        paper_ids: IDs of papers that form the subgraph nodes.
        edges: (citing_paper_id, cited_paper_id) pairs within paper_ids.
        scores: Combined score per paper_id for path ranking.

    Returns:
        List of paper_id paths, each ordered oldest → newest.
    """
    return extract_dag_paths(
        node_ids=paper_ids,
        edges=[(cited, citing) for citing, cited in edges],
        scores=scores,
        min_path_length=_MIN_BACKBONE_LENGTH,
    )


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
        validate_unit_weights(alpha=alpha)
        validate_positive_int("top_k", top_k)
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
        papers_map = build_papers_map(subgraph)
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
        sort_scored_papers(scored)
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
