from abc import ABC, abstractmethod

from aievograph.domain.models import NormalizationMap


class NormalizationMapStorePort(ABC):
    """Domain port for persisting and loading a NormalizationMap across ingest runs."""

    @abstractmethod
    def load(self) -> NormalizationMap:
        """Return the stored NormalizationMap, or an empty NormalizationMap if absent."""
        raise NotImplementedError

    @abstractmethod
    def save(self, norm_map: NormalizationMap) -> None:
        """Persist norm_map so future runs can load it."""
        raise NotImplementedError
