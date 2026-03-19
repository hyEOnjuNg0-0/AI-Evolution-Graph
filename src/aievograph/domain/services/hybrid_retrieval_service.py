"""
VectorRetrievalService  +  GraphRepositoryPort
              ↓
HybridRetrievalService  (Layer B — Hybrid Retrieval, Step 3.3)
              ↓
  search(query, query_type, top_k, hops) → Subgraph

Pipeline:
  [1] VectorRetrievalService.search(query, top_k)          → semantic candidates (seeds)
  [2] GraphRepositoryPort.get_citation_neighborhood_with_distances(seed_id, hops)
                                                            → structural neighbors + hop distances
  [3] Union of candidates
      - vector candidate: semantic_sim = cosine_score, graph_prox = 1.0 (seed, hop=0)
      - graph candidate:  semantic_sim = 0.0,          graph_prox = 1/hop_dist
  [4] hybrid_score = α × semantic_sim + β × graph_prox
  [5] Sort descending, top_k → Subgraph
"""

import logging
from typing import Literal

from aievograph.domain.models import ScoredPaper, Subgraph
from aievograph.domain.ports.graph_repository import GraphRepositoryPort
from aievograph.domain.services.vector_retrieval_service import VectorRetrievalService

logger = logging.getLogger(__name__)

QueryType = Literal["semantic", "structural", "balanced"]

# (alpha, beta) pairs per query type
_QUERY_WEIGHTS: dict[str, tuple[float, float]] = {
    "semantic":   (0.9, 0.1),
    "structural": (0.1, 0.9),
    "balanced":   (0.5, 0.5),
}

# Upper bound matches GraphRetrievalService._MAX_HOPS to prevent exponential fan-out.
_MAX_HOPS = 5


def _graph_proximity(hop_dist: int) -> float:
    """Inverse decay: 1.0 for hop 0 (seed) or hop 1, 0.5 for hop 2, etc.

    Formula: 1.0 / max(hop_dist, 1)
    """
    return 1.0 / max(hop_dist, 1)


class HybridRetrievalService:
    """Combine semantic similarity and graph proximity into a single hybrid score."""

    def __init__(
        self,
        vector_service: VectorRetrievalService,
        graph_repo: GraphRepositoryPort,
    ) -> None:
        self._vector_service = vector_service
        self._graph_repo = graph_repo

    def search(
        self,
        query: str,
        query_type: QueryType = "balanced",
        top_k: int = 10,
        hops: int = 1,
        alpha: float | None = None,
        beta: float | None = None,
    ) -> Subgraph:
        """Return a top-k Subgraph scored by hybrid_score = α × semantic_sim + β × graph_prox.

        Args:
            query: Natural-language query text.
            query_type: One of "semantic", "structural", "balanced" — controls default α/β.
            top_k: Maximum number of papers in the output subgraph.
            hops: Citation expansion depth for graph retrieval (1 ≤ hops ≤ _MAX_HOPS).
            alpha: Override α weight (uses query_type default if None).
            beta: Override β weight (uses query_type default if None).

        Returns:
            Subgraph with papers sorted by hybrid_score descending.

        Raises:
            ValueError: On empty query, invalid query_type, non-positive top_k/hops,
                        or hops exceeding _MAX_HOPS.
        """
        if not query.strip():
            raise ValueError("query must not be empty")
        if query_type not in _QUERY_WEIGHTS:
            raise ValueError(
                f"Unknown query_type: {query_type!r}. Must be one of {list(_QUERY_WEIGHTS)}"
            )
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")
        if hops <= 0:
            raise ValueError(f"hops must be a positive integer, got {hops}")
        if hops > _MAX_HOPS:
            raise ValueError(f"hops must not exceed {_MAX_HOPS}, got {hops}")

        # Resolve weights: explicit override takes precedence over query_type defaults.
        base_alpha, base_beta = _QUERY_WEIGHTS[query_type]
        a = alpha if alpha is not None else base_alpha
        b = beta if beta is not None else base_beta

        # Step 1: Vector search — semantic candidates become graph expansion seeds.
        vector_results = self._vector_service.search(query, top_k=top_k)

        # Accumulate candidates: paper_id → Paper, semantic score, minimum hop distance.
        papers: dict[str, object] = {}   # paper_id → Paper
        semantic_scores: dict[str, float] = {}
        graph_distances: dict[str, int] = {}

        for sp in vector_results:
            pid = sp.paper.paper_id
            papers[pid] = sp.paper
            semantic_scores[pid] = sp.score
            graph_distances[pid] = 0  # seeds are at hop distance 0

        # Step 2: Graph expansion from each seed.
        for seed_sp in vector_results:
            seed_id = seed_sp.paper.paper_id
            neighbors = self._graph_repo.get_citation_neighborhood_with_distances(
                seed_id, hops
            )
            for neighbor_paper, hop_dist in neighbors:
                pid = neighbor_paper.paper_id
                if pid not in papers:
                    papers[pid] = neighbor_paper
                # Keep minimum hop distance across all seeds.
                if pid not in graph_distances or hop_dist < graph_distances[pid]:
                    graph_distances[pid] = hop_dist

        # Steps 3–4: Score all candidates.
        scored: list[ScoredPaper] = []
        for pid, paper in papers.items():  # type: ignore[assignment]
            sem_sim = semantic_scores.get(pid, 0.0)
            hop = graph_distances.get(pid)
            g_prox = _graph_proximity(hop) if hop is not None else 0.0
            score = a * sem_sim + b * g_prox
            scored.append(ScoredPaper(paper=paper, score=score))  # type: ignore[arg-type]

        # Step 5: Sort descending, take top_k.
        scored.sort(key=lambda sp: sp.score, reverse=True)
        logger.debug(
            "Hybrid search for %r (type=%s, α=%.2f, β=%.2f, hops=%d) → %d/%d papers selected",
            query,
            query_type,
            a,
            b,
            hops,
            min(top_k, len(scored)),
            len(scored),
        )
        return Subgraph(papers=scored[:top_k])
