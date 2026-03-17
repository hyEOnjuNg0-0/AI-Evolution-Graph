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

    def build_method_graph(self, papers: list[Paper]) -> NormalizationMap:
        """Extract methods and relations from abstracts, normalize, and persist to graph.

        Returns the NormalizationMap so callers can inspect which entities were merged.
        """
        logger.info("Starting method graph build for %d papers.", len(papers))

        # Step 1: extract method entities + relations from abstracts (LLM)
        raw_results = self._extraction.extract_from_papers(papers)
        logger.info("Extracted method data from %d papers with abstracts.", len(raw_results))
ㅌ
        # Step 2: normalize entity names globally across all papers
        normalized_results, norm_map = self._normalization.normalize(raw_results)
        logger.info("Normalization map has %d entries.", len(norm_map.mapping))

        # Step 3: persist Method nodes, USES edges, and typed method relation edges
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
