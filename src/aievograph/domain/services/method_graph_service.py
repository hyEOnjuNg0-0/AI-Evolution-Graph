"""
Paper list (with abstracts)
    ↓
MethodGraphService.build_method_graph()
    ↓
  1. MethodExtractionService.extract_from_papers()   – LLM extraction per paper
  2. EntityNormalizationService.normalize()           – global entity normalization
  3. repo.upsert_method × N                           – write Method nodes
     repo.create_paper_uses_method × M               – write (:Paper)-[:USES]->(:Method)
     repo.create_method_relation × K                 – write IMPROVES/EXTENDS/REPLACES edges
"""

import logging

from aievograph.domain.models import NormalizationMap, Paper
from aievograph.domain.ports.graph_repository import GraphRepositoryPort
from aievograph.domain.ports.normalization_map_store import NormalizationMapStorePort
from aievograph.domain.services.entity_normalization_service import EntityNormalizationService
from aievograph.domain.services.method_extraction_service import MethodExtractionService

logger = logging.getLogger(__name__)


class MethodGraphService:
    """Domain service that builds the Method Evolution Graph from a paper list."""

    def __init__(
        self,
        repo: GraphRepositoryPort,
        extraction_service: MethodExtractionService,
        normalization_service: EntityNormalizationService,
    ) -> None:
        self._repo = repo
        self._extraction = extraction_service
        self._normalization = normalization_service

    def build_method_graph(
        self,
        papers: list[Paper],
        map_store: NormalizationMapStorePort | None = None,
    ) -> NormalizationMap:
        """Extract methods and relations from abstracts, normalize, and persist to graph.

        When map_store is provided, the NormalizationMap from previous runs is loaded
        before normalization so that known variant→canonical pairs are reused without
        an LLM call.  The resulting map is saved back to the store after normalization.

        Returns the NormalizationMap so callers can inspect which entities were merged.
        """
        logger.info("Starting method graph build for %d papers.", len(papers))

        # Step 1: extract method entities + relations from abstracts (LLM)
        raw_results = self._extraction.extract_from_papers(papers)
        logger.info("Extracted method data from %d papers with abstracts.", len(raw_results))

        # Step 2: normalize entity names, optionally seeded with a persistent map.
        # Accumulate: merge existing entries with this run's new entries before saving
        # so that variants discovered in earlier runs are not lost when a later run's
        # batch does not happen to contain those same names.
        existing_map = map_store.load() if map_store else None
        normalized_results, norm_map = self._normalization.normalize(raw_results, existing_map)
        if map_store:
            accumulated = NormalizationMap(
                mapping={**(existing_map.mapping if existing_map else {}), **norm_map.mapping}
            )
            map_store.save(accumulated)
        logger.info("Normalization map has %d entries.", len(norm_map.mapping))

        # Step 3: persist Method nodes, USES edges, and typed method relation edges.
        # NOTE: the map is saved before graph writes.  If graph writes fail mid-way,
        # the stored map may reference canonical names not yet present in the graph.
        # This is an acceptable trade-off: the stored map is purely advisory for
        # future normalization runs; Phase 1 dedup_methods.py corrects any structural
        # inconsistencies in the graph itself.
        method_count = 0
        uses_count = 0
        relation_count = 0
        for paper_id, result in normalized_results:
            for method in result.methods:
                self._repo.upsert_method(method)
                self._repo.create_paper_uses_method(paper_id, method.name)
                method_count += 1
                uses_count += 1
            for relation in result.relations:
                self._repo.create_method_relation(relation)
                relation_count += 1

        logger.info(
            "Persisted %d method nodes, %d USES edges, %d relation edges.",
            method_count,
            uses_count,
            relation_count,
        )
        return norm_map
