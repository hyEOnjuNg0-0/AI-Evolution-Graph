"""
neo4j.Driver
        ↓
Neo4jMethodTrendRepository  (implements MethodTrendRepositoryPort)
        ↓
  get_yearly_usage_counts(method_names, year_start, year_end)
      → dict[method_name, dict[year, count]]
  get_venue_distribution(method_names, year_start, year_end)
      → dict[method_name, dict[venue, count]]

Both queries traverse (:Paper)-[:USES]->(:Method) edges, filtering by method name
and paper publication year.
"""

import logging

from neo4j import Driver

from aievograph.domain.ports.method_trend_repository import MethodTrendRepositoryPort
from aievograph.infrastructure.neo4j_utils import run_grouped_query

logger = logging.getLogger(__name__)

# Count papers using each method, grouped by publication year.
_YEARLY_USAGE = """
MATCH (p:Paper)-[:USES]->(m:Method)
WHERE m.name IN $method_names
  AND p.publication_year >= $year_start
  AND p.publication_year <= $year_end
RETURN m.name               AS method_name,
       p.publication_year   AS year,
       count(p)             AS cnt
"""

# Count papers using each method, grouped by venue (null venues excluded).
_VENUE_DISTRIBUTION = """
MATCH (p:Paper)-[:USES]->(m:Method)
WHERE m.name IN $method_names
  AND p.publication_year >= $year_start
  AND p.publication_year <= $year_end
  AND p.venue IS NOT NULL
RETURN m.name   AS method_name,
       p.venue  AS venue,
       count(p) AS cnt
"""


class Neo4jMethodTrendRepository(MethodTrendRepositoryPort):
    """Fetch method adoption data from Neo4j for trend momentum scoring."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def get_yearly_usage_counts(
        self,
        method_names: list[str],
        year_start: int,
        year_end: int,
    ) -> dict[str, dict[int, int]]:
        """Return {method_name: {year: count}} for paper usages within the window."""
        if year_end < year_start:
            raise ValueError(
                f"year_end ({year_end}) must be >= year_start ({year_start})"
            )
        if not method_names:
            return {}

        result: dict[str, dict[int, int]] = run_grouped_query(
            self._driver,
            _YEARLY_USAGE,
            {"method_names": method_names, "year_start": year_start, "year_end": year_end},
            group_key="method_name",
            sub_key="year",
            sub_key_cast=int,
        )

        logger.debug(
            "Yearly usage fetched: %d/%d methods have data in %d–%d",
            len(result),
            len(method_names),
            year_start,
            year_end,
        )
        return result

    def get_venue_distribution(
        self,
        method_names: list[str],
        year_start: int,
        year_end: int,
    ) -> dict[str, dict[str, int]]:
        """Return {method_name: {venue: count}} for paper usages within the window."""
        if year_end < year_start:
            raise ValueError(
                f"year_end ({year_end}) must be >= year_start ({year_start})"
            )
        if not method_names:
            return {}

        result: dict[str, dict[str, int]] = run_grouped_query(
            self._driver,
            _VENUE_DISTRIBUTION,
            {"method_names": method_names, "year_start": year_start, "year_end": year_end},
            group_key="method_name",
            sub_key="venue",
        )

        logger.debug(
            "Venue distribution fetched: %d/%d methods have venue data in %d–%d",
            len(result),
            len(method_names),
            year_start,
            year_end,
        )
        return result
