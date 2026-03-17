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
    def get_papers_by_year_range(self, start_year: int, end_year: int) -> list[Paper]:
        """Return all Paper nodes whose publication_year falls within [start_year, end_year]."""
        raise NotImplementedError

    @abstractmethod
    def create_method_relation(self, relation: MethodRelation) -> None:
        """Create a typed edge between two Method nodes (IMPROVES / EXTENDS / REPLACES)."""
        raise NotImplementedError

    @abstractmethod
    def create_paper_uses_method(self, paper_id: str, method_name: str) -> None:
        """Create a USES edge from a Paper node to a Method node."""
        raise NotImplementedError
