from abc import ABC, abstractmethod


class MethodEvolutionRepositoryPort(ABC):
    """Domain port for fetching Method Evolution Graph structure.

    Used by EvolutionPathService to traverse method-to-method relation edges
    and to map papers (breakthrough candidates) back to the methods they use.
    """

    @abstractmethod
    def get_relations(
        self,
        method_names: list[str],
    ) -> list[tuple[str, str, str]]:
        """Return method-relation edges whose both endpoints are in method_names.

        Only edges of type IMPROVES, EXTENDS, or REPLACES are returned.

        Args:
            method_names: Canonical method names that form the analysis subgraph.

        Returns:
            List of (source_method, target_method, relation_type) triples.
            source_method is the NEWER method (it improves/extends/replaces target).
            target_method is the OLDER method being built upon.
            Only edges where both endpoints are in method_names are included.
        """
        raise NotImplementedError

    @abstractmethod
    def get_paper_methods(
        self,
        paper_ids: list[str],
    ) -> dict[str, list[str]]:
        """Return the methods used by each paper.

        Args:
            paper_ids: Paper IDs whose USES edges to retrieve.

        Returns:
            Dict mapping paper_id → list of canonical method names.
            Papers with no USES edges may be absent from the result.
        """
        raise NotImplementedError
