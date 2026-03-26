"""
neo4j.Driver
        ↓
Neo4jCitationTimeSeriesRepository  (implements CitationTimeSeriesRepositoryPort)
        ↓
  get_yearly_citation_counts(paper_ids, year_start, year_end)
      → dict[paper_id, dict[year, count]]

Cypher: count CITES edges whose citing paper's publication_year falls in [year_start, year_end].
Groups by cited paper_id and citing publication_year.
"""

import logging

from neo4j import Driver

from aievograph.domain.ports.citation_time_series_repository import (
    CitationTimeSeriesRepositoryPort,
)
from aievograph.infrastructure.neo4j_utils import run_grouped_query

logger = logging.getLogger(__name__)

# For each cited paper in paper_ids, count how many citing papers published
# in [year_start, year_end] reference it, grouped by citing year.
_YEARLY_CITATION_COUNTS = """
MATCH (cited:Paper)<-[:CITES]-(citing:Paper)
WHERE cited.paper_id IN $paper_ids
  AND citing.publication_year >= $year_start
  AND citing.publication_year <= $year_end
RETURN cited.paper_id        AS paper_id,
       citing.publication_year AS year,
       count(*)               AS cnt
"""


class Neo4jCitationTimeSeriesRepository(CitationTimeSeriesRepositoryPort):
    """Fetch yearly citation counts from Neo4j for breakthrough detection."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def get_yearly_citation_counts(
        self,
        paper_ids: list[str],
        year_start: int,
        year_end: int,
    ) -> dict[str, dict[int, int]]:
        """Return {paper_id: {year: count}} for incoming citations within the window.

        Papers with no citations in the window are absent from the result;
        callers should treat them as all-zero series.
        """
        if not paper_ids:
            return {}

        result: dict[str, dict[int, int]] = run_grouped_query(
            self._driver,
            _YEARLY_CITATION_COUNTS,
            {"paper_ids": paper_ids, "year_start": year_start, "year_end": year_end},
            group_key="paper_id",
            sub_key="year",
            sub_key_cast=int,
        )

        logger.debug(
            "Citation time series fetched: %d/%d papers have data in %d–%d",
            len(result),
            len(paper_ids),
            year_start,
            year_end,
        )
        return result
