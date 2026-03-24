"""
CentralityRepositoryPort
        ↓
CentralityRankingService  (Layer C — Centrality-based Ranking, Step 4.1)
        ↓
  rank(subgraph, gamma)           → list[ScoredPaper]
  score_breakdown(subgraph, gamma)→ list[CentralityScores]

Shared pipeline (_compute_scores):
  [1] Extract paper_ids from the input Subgraph
  [2] CentralityRepositoryPort.compute_centralities(paper_ids)
      → (raw PageRank scores, raw Betweenness scores) in one GDS projection
  [3] Fill missing paper_ids with 0.0
  [4] Max-normalize each score dict to [0, 1]; clip negatives to 0
  [5] combined = γ × pagerank_norm + (1 − γ) × betweenness_norm
  [6] Return sorted list of CentralityScores
"""

import logging

from aievograph.domain.models import CentralityScores, ScoredPaper, Subgraph
from aievograph.domain.ports.centrality_repository import CentralityRepositoryPort

logger = logging.getLogger(__name__)

_DEFAULT_GAMMA = 0.6  # weight given to PageRank vs Betweenness


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    """Max-normalize a score dict to [0, 1].

    Negative values are clipped to 0 before normalization.
    Returns all-zeros if the maximum is 0 or below.
    """
    max_val = max(scores.values(), default=0.0)
    if max_val <= 0.0:
        return {k: 0.0 for k in scores}
    return {k: max(0.0, v) / max_val for k, v in scores.items()}


class CentralityRankingService:
    """Rank papers in a Subgraph by structural importance using GDS centrality."""

    def __init__(self, repo: CentralityRepositoryPort) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank(
        self,
        subgraph: Subgraph,
        gamma: float = _DEFAULT_GAMMA,
    ) -> list[ScoredPaper]:
        """Rank subgraph papers by combined centrality score.

        Args:
            subgraph: Candidate papers from Layer B hybrid retrieval.
            gamma: Weight for PageRank in [0, 1]; (1 − gamma) goes to Betweenness.

        Returns:
            Papers as ScoredPaper list sorted by combined_score descending.
            paper_id is a deterministic tiebreaker.

        Raises:
            ValueError: If gamma is outside [0.0, 1.0].
        """
        scores = self._compute_scores(subgraph, gamma)
        papers_map = {sp.paper.paper_id: sp.paper for sp in subgraph.papers}
        result = [
            ScoredPaper(paper=papers_map[c.paper_id], score=c.combined_score)
            for c in scores
        ]
        if result:
            logger.debug(
                "Centrality ranking: %d papers, γ=%.2f → top=%s (score=%.4f)",
                len(result),
                gamma,
                result[0].paper.paper_id,
                result[0].score,
            )
        return result

    def score_breakdown(
        self,
        subgraph: Subgraph,
        gamma: float = _DEFAULT_GAMMA,
    ) -> list[CentralityScores]:
        """Return per-paper centrality breakdown (pagerank, betweenness, combined).

        Useful for inspection and downstream combination with other ranking signals
        (e.g. Step 4.3 combined ranking).

        Args:
            subgraph: Candidate papers from Layer B hybrid retrieval.
            gamma: Weight for PageRank (same semantics as rank()).

        Returns:
            List of CentralityScores sorted by combined_score descending.

        Raises:
            ValueError: If gamma is outside [0.0, 1.0].
        """
        return self._compute_scores(subgraph, gamma)

    # ------------------------------------------------------------------
    # Shared pipeline
    # ------------------------------------------------------------------

    def _compute_scores(
        self,
        subgraph: Subgraph,
        gamma: float,
    ) -> list[CentralityScores]:
        """Shared pipeline: fetch → normalize → combine → sort.

        Returns CentralityScores sorted by combined_score descending.
        """
        if not (0.0 <= gamma <= 1.0):
            raise ValueError(f"gamma must be in [0.0, 1.0], got {gamma}")
        if not subgraph.papers:
            return []

        paper_ids = [sp.paper.paper_id for sp in subgraph.papers]

        # Single GDS call — one projection for both algorithms.
        pr_raw, bw_raw = self._repo.compute_centralities(paper_ids)

        # Fill missing entries (papers with no graph edges).
        for pid in paper_ids:
            pr_raw.setdefault(pid, 0.0)
            bw_raw.setdefault(pid, 0.0)

        pr_norm = _normalize(pr_raw)
        bw_norm = _normalize(bw_raw)

        result: list[CentralityScores] = [
            CentralityScores(
                paper_id=pid,
                pagerank=pr_norm.get(pid, 0.0),
                betweenness=bw_norm.get(pid, 0.0),
                combined_score=gamma * pr_norm.get(pid, 0.0)
                + (1.0 - gamma) * bw_norm.get(pid, 0.0),
            )
            for pid in paper_ids
        ]
        result.sort(key=lambda c: (-c.combined_score, c.paper_id))
        return result
