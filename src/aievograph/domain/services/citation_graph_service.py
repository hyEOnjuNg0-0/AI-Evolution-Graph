"""
Paper list
    ↓
CitationGraphService.build_citation_graph()
    ↓
  1. create_indexes          – ensures DB indexes exist
  2. upsert_paper × N        – write all Paper + Author nodes
  3. create_citation × M     – write CITES edges (only between collected papers)
"""

import logging

from aievograph.domain.models import Citation, Paper
from aievograph.domain.ports.graph_repository import GraphRepositoryPort

logger = logging.getLogger(__name__)


class CitationGraphService:
    """Domain service that builds the Temporal Citation Graph from a paper list."""

    def __init__(self, repo: GraphRepositoryPort) -> None:
        self._repo = repo

    def build_citation_graph(self, papers: list[Paper]) -> None:
        """Persist papers and their citation edges to the graph store.

        Only edges between papers present in *papers* are created, so the
        resulting graph is a closed subgraph of the collected dataset.
        """
        known_ids: set[str] = {p.paper_id for p in papers}

        logger.info("Building citation graph for %d papers.", len(papers))

        # Step 1: ensure indexes exist before writing bulk data
        self._repo.create_indexes()

        # Step 2: persist every paper (+ its authors)
        for paper in papers:
            self._repo.upsert_paper(paper)

        logger.info("Upserted %d paper nodes.", len(papers))

        # Step 3: create CITES edges only between collected papers
        citation_count = 0
        for paper in papers:
            for cited_id in paper.referenced_work_ids:
                if cited_id not in known_ids:
                    # Skip references to papers outside the collected set
                    continue
                citation = Citation(
                    citing_paper_id=paper.paper_id,
                    cited_paper_id=cited_id,
                    created_year=paper.publication_year,
                )
                self._repo.create_citation(citation)
                citation_count += 1

        logger.info("Created %d citation edges.", citation_count)
