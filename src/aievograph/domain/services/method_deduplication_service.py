"""Service that detects and merges duplicate Method nodes in the graph."""

import logging

from aievograph.domain.models import Method, NormalizationMap
from aievograph.domain.ports.entity_normalizer import EntityNormalizerPort
from aievograph.domain.ports.graph_repository import GraphRepositoryPort

logger = logging.getLogger(__name__)


class MethodDeduplicationService:
    """Reads all Method names from the graph, normalizes them, and merges duplicates."""

    def __init__(self, repo: GraphRepositoryPort, normalizer: EntityNormalizerPort) -> None:
        self._repo = repo
        self._normalizer = normalizer

    def plan(self) -> NormalizationMap:
        """Return the normalization map without modifying the graph (dry-run).

        Identical to the first two steps of deduplicate() — useful for previewing
        which nodes would be merged before committing changes.
        """
        names = self._repo.get_all_method_names()
        logger.info("Plan: fetched %d method names from the graph.", len(names))
        methods = [Method(name=n, method_type="Method") for n in names]
        return self._normalizer.normalize(methods)

    def deduplicate(self) -> NormalizationMap:
        """Merge duplicate Method nodes in the graph.

        1. Fetch all Method node names from the repository.
        2. Build a NormalizationMap via the normalizer.
        3. For each (variant → canonical) pair, merge the variant into the canonical.

        Returns the NormalizationMap so callers can inspect what was merged.
        """
        names = self._repo.get_all_method_names()
        logger.info("Fetched %d method names from the graph.", len(names))

        # Wrap raw names as Method objects (method_type default is arbitrary; only name matters)
        methods = [Method(name=n, method_type="Method") for n in names]
        norm_map: NormalizationMap = self._normalizer.normalize(methods)
        logger.info("Normalization map produced %d variant→canonical pairs.", len(norm_map.mapping))

        return self.apply(norm_map)

    def apply(self, norm_map: NormalizationMap) -> NormalizationMap:
        """Apply a pre-computed NormalizationMap to the graph without calling the LLM.

        Useful when --dry-run was run first and the plan was saved to a file.
        Returns the same map so callers can inspect what was merged.
        """
        for variant, canonical in norm_map.mapping.items():
            if variant == canonical:
                continue
            logger.info("Merging '%s' → '%s'.", variant, canonical)
            self._repo.merge_method_nodes(canonical, variant)

        return norm_map
