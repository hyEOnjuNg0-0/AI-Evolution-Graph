"""
CentralityRepositoryPort
        ↓
CentralityRankingService  (Layer C — Centrality-based Ranking, Step 4.1)
        ↓
  rank(subgraph, gamma) → list[ScoredPaper]

Pipeline:
  [1] Extract paper_ids from the input Subgraph
  [2] CentralityRepositoryPort.compute_pagerank(paper_ids)   → raw PageRank scores
  [3] CentralityRepositoryPort.compute_betweenness(paper_ids)→ raw Betweenness scores
  [4] Normalize each score set to [0, 1] (max-normalization)
  [5] combined = γ × pagerank_norm + (1 − γ) × betweenness_norm
  [6] Return papers as ScoredPaper list sorted by combined score descending
"""

import logging

from aievograph.domain.models import CentralityScores, ScoredPaper, Subgraph
from aievograph.domain.ports.centrality_repository import CentralityRepositoryPort

logger = logging.getLogger(__name__)

_DEFAULT_GAMMA = 0.6  # weight given to PageRank vs Betweenness


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    """Max-normalize a score dict to [0, 1]. Returns zeros if all values are 0."""
    max_val = max(scores.values(), default=0.0)
    if max_val == 0.0:
        return {k: 0.0 for k in scores}
    return {k: v / max_val for k, v in scores.items()}


class CentralityRankingService:
    """Rank papers in a Subgraph by structural importance using GDS centrality."""

    def __init__(self, repo: CentralityRepositoryPort) -> None:
        self._repo = repo

    def rank(
        self,
        subgraph: Subgraph,
        gamma: float = _DEFAULT_GAMMA,
    ) -> list[ScoredPaper]:
        """Rank subgraph papers by combined centrality score.

        Args:
            subgraph: Candidate papers from Layer B hybrid retrieval.
            gamma: Weight for PageRank in the combined score (0 ≤ γ ≤ 1).
                   (1 − gamma) is the weight for Betweenness Centrality.

        Returns:
            Papers sorted by combined_score descending.
            paper_id is a deterministic tiebreaker.

        Raises:
            ValueError: If gamma is outside [0.0, 1.0] or subgraph is empty.
        """
        if not (0.0 <= gamma <= 1.0):
            raise ValueError(f"gamma must be in [0.0, 1.0], got {gamma}")
        if not subgraph.papers:
            return []

        paper_ids = [sp.paper.paper_id for sp in subgraph.papers]
        papers_map = {sp.paper.paper_id: sp.paper for sp in subgraph.papers}

        # Steps 2–3: Fetch raw centrality scores from GDS.
        pr_raw = self._repo.compute_pagerank(paper_ids)
        bw_raw = self._repo.compute_betweenness(paper_ids)

        # Ensure every paper_id has an entry (absent means no graph edges → score 0).
        for pid in paper_ids:
            pr_raw.setdefault(pid, 0.0)
            bw_raw.setdefault(pid, 0.0)

        # Step 4: Normalize.
        pr_norm = _normalize(pr_raw)
        bw_norm = _normalize(bw_raw)

        # Steps 5–6: Combine and sort.
        scored: list[ScoredPaper] = []
        for pid, paper in papers_map.items():
            pr = pr_norm.get(pid, 0.0)
            bw = bw_norm.get(pid, 0.0)
            combined = gamma * pr + (1.0 - gamma) * bw
            scored.append(ScoredPaper(paper=paper, score=combined))

        scored.sort(key=lambda sp: (-sp.score, sp.paper.paper_id))

        logger.debug(
            "Centrality ranking: %d papers, γ=%.2f → top paper_id=%s (score=%.4f)",
            len(scored),
            gamma,
            scored[0].paper.paper_id if scored else "—",
            scored[0].score if scored else 0.0,
        )
        return scored

    def score_breakdown(
        self,
        subgraph: Subgraph,
        gamma: float = _DEFAULT_GAMMA,
    ) -> list[CentralityScores]:
        """Return per-paper centrality breakdown (pagerank, betweenness, combined).

        Useful for inspection and downstream combination with other ranking signals.

        Args:
            subgraph: Candidate papers from Layer B hybrid retrieval.
            gamma: Weight for PageRank (same as in rank()).

        Returns:
            List of CentralityScores sorted by combined_score descending.

        Raises:
            ValueError: If gamma is outside [0.0, 1.0].
        """
        if not (0.0 <= gamma <= 1.0):
            raise ValueError(f"gamma must be in [0.0, 1.0], got {gamma}")
        if not subgraph.papers:
            return []

        paper_ids = [sp.paper.paper_id for sp in subgraph.papers]

        pr_raw = self._repo.compute_pagerank(paper_ids)
        bw_raw = self._repo.compute_betweenness(paper_ids)

        for pid in paper_ids:
            pr_raw.setdefault(pid, 0.0)
            bw_raw.setdefault(pid, 0.0)

        pr_norm = _normalize(pr_raw)
        bw_norm = _normalize(bw_raw)

        result: list[CentralityScores] = []
        for pid in paper_ids:
            pr = pr_norm.get(pid, 0.0)
            bw = bw_norm.get(pid, 0.0)
            result.append(
                CentralityScores(
                    paper_id=pid,
                    pagerank=pr,
                    betweenness=bw,
                    combined_score=gamma * pr + (1.0 - gamma) * bw,
                )
            )

        result.sort(key=lambda c: (-c.combined_score, c.paper_id))
        return result
