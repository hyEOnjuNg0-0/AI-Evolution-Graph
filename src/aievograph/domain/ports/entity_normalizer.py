from abc import ABC, abstractmethod

from aievograph.domain.models import Method, NormalizationMap


class EntityNormalizerPort(ABC):
    """Domain port for deduplicating and normalizing Method entity names."""

    @abstractmethod
    def normalize(self, methods: list[Method]) -> NormalizationMap:
        """Return a NormalizationMap mapping variant names to canonical names."""
        raise NotImplementedError
