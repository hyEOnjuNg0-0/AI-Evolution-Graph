from abc import ABC, abstractmethod

from aievograph.domain.models import Paper


class PaperCollectorPort(ABC):
    """Domain port for collecting papers from external sources."""

    @abstractmethod
    async def collect(
        self,
        venues: list[str],
        year_start: int,
        year_end: int,
    ) -> list[Paper]:
        """Collect papers filtered by venue name and year range."""
        raise NotImplementedError
