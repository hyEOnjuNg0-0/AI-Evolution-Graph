from abc import ABC, abstractmethod

from aievograph.domain.models import ExtractionResult


class MethodExtractorPort(ABC):
    """Domain port for LLM-based method entity and relation extraction."""

    @abstractmethod
    def extract(self, abstract: str) -> ExtractionResult:
        """Extract Method entities and evolutionary relations from a paper abstract."""
        raise NotImplementedError
