from abc import ABC, abstractmethod


class SubgraphEdgeRepositoryPort(ABC):
    """Domain port for fetching citation edges within a paper subgraph.

    Used by the combined ranking service to build the citation DAG
    needed for backbone (research lineage) extraction.
    """

    @abstractmethod
    def get_citation_edges(
        self, paper_ids: list[str]
    ) -> list[tuple[str, str]]:
        """Return citation edges whose both endpoints are in paper_ids.

        Args:
            paper_ids: IDs of papers that form the subgraph.

        Returns:
            List of (citing_paper_id, cited_paper_id) tuples.
            Only edges where both citing and cited are in paper_ids
            are included.
        """
        raise NotImplementedError
