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
        existing_map: NormalizationMap | None = None,
    ) -> tuple[list[tuple[str, ExtractionResult]], NormalizationMap]:
        """Normalize method names globally across all papers.

        When existing_map is provided, names that already have an exact mapping
        in existing_map are pre-mapped without calling the LLM.  Only the
        remaining (unmapped) names are sent to the normalizer for clustering.
        This prevents cross-batch duplicates from accumulating when the same
        variant appears in a later ingest run.

        Returns the updated results and the combined NormalizationMap (existing
        pre-mapped entries merged with any new LLM-derived entries).
        """
        # Collect unique methods across all papers (first-seen description wins)
        all_methods: dict[str, Method] = {}
        for _, result in results:
            for method in result.methods:
                if method.name not in all_methods:
                    all_methods[method.name] = method

        if existing_map is not None:
            # Split into pre-mapped (exact match in existing_map) and unmapped.
            pre_mapped: dict[str, str] = {}
            unmapped_methods: dict[str, Method] = {}
            for name, method in all_methods.items():
                canonical = existing_map.normalize(name)
                if canonical != name:
                    pre_mapped[name] = canonical
                else:
                    unmapped_methods[name] = method

            new_norm_map = self._normalizer.normalize(list(unmapped_methods.values()))
            norm_map = NormalizationMap(mapping={**pre_mapped, **new_norm_map.mapping})
            logger.info(
                "Normalization: %d pre-mapped (existing), %d new from LLM.",
                len(pre_mapped),
                len(new_norm_map.mapping),
            )
        else:
            norm_map = self._normalizer.normalize(list(all_methods.values()))
            logger.info("Normalization map size: %d entries", len(norm_map.mapping))

        normalized = [
            (paper_id, _apply_map(result, norm_map))
            for paper_id, result in results
        ]
        return normalized, norm_map
