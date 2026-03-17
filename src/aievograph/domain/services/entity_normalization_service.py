"""Service that applies entity normalization consistently across all extraction results."""

import logging

from aievograph.domain.models import (
    ExtractionResult,
    Method,
    MethodRelation,
    NormalizationMap,
)
from aievograph.domain.ports.entity_normalizer import EntityNormalizerPort

logger = logging.getLogger(__name__)


def _apply_map(
    result: ExtractionResult, norm_map: NormalizationMap
) -> ExtractionResult:
    """Return a new ExtractionResult with all method names replaced by canonical forms."""
    # Normalize methods, keeping one entry per canonical name (first occurrence wins)
    canonical_methods: dict[str, Method] = {}
    for method in result.methods:
        canonical = norm_map.normalize(method.name)
        if canonical not in canonical_methods:
            canonical_methods[canonical] = (
                method
                if canonical == method.name
                else Method(
                    name=canonical,
                    method_type=method.method_type,
                    description=method.description,
                )
            )

    # Normalize relation endpoints and deduplicate
    seen: set[tuple[str, str, str]] = set()
    normalized_relations: list[MethodRelation] = []
    for rel in result.relations:
        src = norm_map.normalize(rel.source_method)
        tgt = norm_map.normalize(rel.target_method)
        key = (src, tgt, rel.relation_type)
        if key not in seen:
            seen.add(key)
            normalized_relations.append(
                MethodRelation(
                    source_method=src,
                    target_method=tgt,
                    relation_type=rel.relation_type,
                    evidence=rel.evidence,
                )
            )

    return ExtractionResult(
        methods=list(canonical_methods.values()),
        relations=normalized_relations,
    )


class EntityNormalizationService:
    def __init__(self, normalizer: EntityNormalizerPort) -> None:
        self._normalizer = normalizer

    def normalize(
        self,
        results: list[tuple[str, ExtractionResult]],
    ) -> tuple[list[tuple[str, ExtractionResult]], NormalizationMap]:
        """Normalize method names globally across all papers.

        Collects every unique Method from all results, builds a NormalizationMap
        via the injected normalizer, then re-applies it to each ExtractionResult.
        Returns the updated results and the map (for persistence / audit).
        """
        # Collect unique methods across all papers (first-seen description wins)
        all_methods: dict[str, Method] = {}
        for _, result in results:
            for method in result.methods:
                if method.name not in all_methods:
                    all_methods[method.name] = method

        norm_map = self._normalizer.normalize(list(all_methods.values()))
        logger.info("Normalization map size: %d entries", len(norm_map.mapping))

        normalized = [
            (paper_id, _apply_map(result, norm_map))
            for paper_id, result in results
        ]
        return normalized, norm_map
