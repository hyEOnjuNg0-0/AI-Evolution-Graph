from abc import ABC, abstractmethod

from aievograph.domain.models import Citation, Method, MethodRelation, Paper


class GraphRepositoryPort(ABC):
    """Domain port for graph persistence."""

    @abstractmethod
    def create_indexes(self) -> None:
        """Create database indexes for efficient lookups and time-range filtering."""
        raise NotImplementedError

    @abstractmethod
    def upsert_paper(self, paper: Paper) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_method(self, method: Method) -> None:
        raise NotImplementedError

    @abstractmethod
    def create_citation(self, citation: Citation) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_papers_by_year_range(
        self, start_year: int, end_year: int, venues: list[str] | None = None
    ) -> list[Paper]:
        """Return Paper nodes within [start_year, end_year], optionally filtered by venue."""
        raise NotImplementedError

    @abstractmethod
    def create_method_relation(self, relation: MethodRelation) -> None:
        """Create a typed edge between two Method nodes (IMPROVES / EXTENDS / REPLACES)."""
        raise NotImplementedError

    @abstractmethod
    def create_paper_uses_method(self, paper_id: str, method_name: str) -> None:
        """Create a USES edge from a Paper node to a Method node."""
        raise NotImplementedError

    @abstractmethod
    def get_paper_by_id(self, paper_id: str) -> "Paper | None":
        """Return the Paper node with the given ID, or None if not found."""
        raise NotImplementedError

    @abstractmethod
    def get_citation_neighborhood(self, paper_id: str, hops: int) -> list["Paper"]:
        """Return Paper nodes reachable within `hops` citation hops from the seed.

        Traversal is bidirectional (follows CITES in both directions).
        The seed paper itself must NOT be included in the result.
        hops must be a positive integer; callers are responsible for enforcing an upper bound.
        Implementations may cap result size internally (e.g. LIMIT).
        """
        raise NotImplementedError
