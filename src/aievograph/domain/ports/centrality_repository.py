from abc import ABC, abstractmethod


class CentralityRepositoryPort(ABC):
    """Domain port for GDS-based centrality computation on a paper subgraph.

    Implementations must override compute_centralities(), which runs both
    PageRank and Betweenness in a single GDS projection to avoid creating
    the same in-memory graph twice.
    """

    @abstractmethod
    def compute_centralities(
        self, paper_ids: list[str]
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Return (pagerank_scores, betweenness_scores) for the given paper subgraph.

        Both dicts share the same key set (paper_ids that exist in the graph).
        Papers absent from the graph may be missing from the result dicts;
        callers are responsible for filling in 0.0 defaults.

        Args:
            paper_ids: IDs of papers that form the subgraph projection.

        Returns:
            Tuple of (pagerank, betweenness) score dicts, each mapping
            paper_id → raw score.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Convenience delegates — override for performance if needed.
    # ------------------------------------------------------------------

    def compute_pagerank(self, paper_ids: list[str]) -> dict[str, float]:
        """Return PageRank scores only. Delegates to compute_centralities()."""
        return self.compute_centralities(paper_ids)[0]

    def compute_betweenness(self, paper_ids: list[str]) -> dict[str, float]:
        """Return betweenness centrality scores only. Delegates to compute_centralities()."""
        return self.compute_centralities(paper_ids)[1]
