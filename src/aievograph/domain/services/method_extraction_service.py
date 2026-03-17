"""Service that coordinates LLM-based method extraction across a collection of papers."""

import logging

from aievograph.domain.models import ExtractionResult, Paper
from aievograph.domain.ports.method_extractor import MethodExtractorPort

logger = logging.getLogger(__name__)


class MethodExtractionService:
    def __init__(self, extractor: MethodExtractorPort) -> None:
        self._extractor = extractor

    def extract_from_papers(
        self, papers: list[Paper]
    ) -> list[tuple[str, ExtractionResult]]:
        """Return (paper_id, ExtractionResult) pairs for each paper that has an abstract."""
        results: list[tuple[str, ExtractionResult]] = []
        for paper in papers:
            if not paper.abstract:
                logger.debug("Skipping paper %s: no abstract", paper.paper_id)
                continue
            result = self._extractor.extract(paper.abstract)
            logger.info(
                "paper=%s methods=%d relations=%d",
                paper.paper_id,
                len(result.methods),
                len(result.relations),
            )
            results.append((paper.paper_id, result))
        return results
