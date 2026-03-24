from abc import ABC, abstractmethod


class CentralityRepositoryPort(ABC):
    """Domain port for GDS-based centrality computation on a paper subgraph."""

    @abstractmethod
    def compute_pagerank(self, paper_ids: list[str]) -> dict[str, float]:
        """Return PageRank score per paper_id, scoped to the given subgraph.

        Args:
            paper_ids: IDs of papers that form the subgraph projection.

        Returns:
            Mapping of paper_id → raw PageRank score.
            Papers with no in-graph edges may return a score of 0.0.
        """
        raise NotImplementedError

    @abstractmethod
    def compute_betweenness(self, paper_ids: list[str]) -> dict[str, float]:
        """Return betweenness centrality score per paper_id, scoped to the given subgraph.

        Args:
            paper_ids: IDs of papers that form the subgraph projection.

        Returns:
            Mapping of paper_id → raw betweenness centrality score.
        """
        raise NotImplementedError
