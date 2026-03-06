from abc import ABC, abstractmethod

from aievograph.domain.models import Citation, Method, Paper


class GraphRepositoryPort(ABC):
    """Domain port for graph persistence."""

    @abstractmethod
    def upsert_paper(self, paper: Paper) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_method(self, method: Method) -> None:
        raise NotImplementedError

    @abstractmethod
    def create_citation(self, citation: Citation) -> None:
        raise NotImplementedError
