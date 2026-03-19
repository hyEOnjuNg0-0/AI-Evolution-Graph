"""
GraphRepositoryPort
        ↓
GraphRetrievalService  (Layer B — Graph Retrieval)
        ↓
  expand_from_id(paper_id, hops) → list[Paper]
    - Validates inputs (paper_id, hops)
    - Verifies seed paper exists (fail fast)
    - Delegates N-hop citation expansion to GraphRepositoryPort
"""

import logging

from aievograph.domain.models import Paper
from aievograph.domain.ports.graph_repository import GraphRepositoryPort

logger = logging.getLogger(__name__)

_DEFAULT_HOPS = 1
# Upper bound prevents exponential fan-out on large graphs (DoS protection).
_MAX_HOPS = 5


class GraphRetrievalService:
    """Retrieve structurally connected papers via N-hop citation expansion."""

    def __init__(self, graph_repo: GraphRepositoryPort) -> None:
        self._repo = graph_repo

    def expand_from_id(self, paper_id: str, hops: int = _DEFAULT_HOPS) -> list[Paper]:
        """Return papers within `hops` citation hops of the seed paper (both CITES directions).

        Args:
            paper_id: The ID of the seed paper.
            hops: Maximum traversal depth (1 <= hops <= _MAX_HOPS).

        Returns:
            Distinct Paper nodes reachable from the seed, excluding the seed itself.

        Raises:
            ValueError: If paper_id is empty/whitespace, hops out of range, or seed not found.
        """
        paper_id = paper_id.strip()
        if not paper_id:
            raise ValueError("paper_id must not be empty")
        if hops <= 0:
            raise ValueError(f"hops must be a positive integer, got {hops}")
        if hops > _MAX_HOPS:
            raise ValueError(f"hops must not exceed {_MAX_HOPS}, got {hops}")

        seed = self._repo.get_paper_by_id(paper_id)
        if seed is None:
            raise ValueError(f"Paper not found: {paper_id}")

        neighbors = self._repo.get_citation_neighborhood(paper_id, hops)
        # Enforce contract: exclude seed even if the repo implementation returns it.
        result = [p for p in neighbors if p.paper_id != paper_id]
        logger.debug(
            "Graph expansion from %s at depth %d returned %d papers",
            paper_id,
            hops,
            len(result),
        )
        return result
