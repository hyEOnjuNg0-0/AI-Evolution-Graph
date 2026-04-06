"""Unit tests for Neo4jMethodTrendRepository using a mocked Neo4j driver.

Covers:
  - get_yearly_usage_counts: correct Cypher, correct result grouping
  - get_venue_distribution: correct Cypher, correct result grouping
  - get_all_yearly_usage_counts: Discovery mode — no name filter, correct Cypher
  - get_all_venue_distributions: Discovery mode — no name filter, correct Cypher
  - Edge cases: empty method_names, invalid year range
"""

import pytest
from unittest.mock import MagicMock

from aievograph.infrastructure.neo4j_method_trend_repository import (
    Neo4jMethodTrendRepository,
    _ALL_VENUE_DISTRIBUTION,
    _ALL_YEARLY_USAGE,
    _VENUE_DISTRIBUTION,
    _YEARLY_USAGE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_driver() -> tuple[MagicMock, MagicMock]:
    """Return (driver_mock, session_mock) with session as a context manager."""
    session = MagicMock()
    driver = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return driver, session


def _make_record(method_name: str, sub_key: str, sub_val, cnt: int) -> MagicMock:
    """Build a mock Neo4j record with method_name, a sub-key, and a count."""
    record = MagicMock()
    record.__getitem__ = lambda self, k: {
        "method_name": method_name,
        sub_key: sub_val,
        "cnt": cnt,
    }[k]
    return record


# ---------------------------------------------------------------------------
# get_yearly_usage_counts
# ---------------------------------------------------------------------------

class TestGetYearlyUsageCounts:
    def test_sends_correct_cypher(self):
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jMethodTrendRepository(driver)
        repo.get_yearly_usage_counts(["Transformer"], 2019, 2023)
        session.run.assert_called_once_with(
            _YEARLY_USAGE,
            method_names=["Transformer"],
            year_start=2019,
            year_end=2023,
        )

    def test_groups_results_by_method_and_year(self):
        driver, session = _make_driver()
        session.run.return_value = [
            _make_record("Transformer", "year", 2020, 5),
            _make_record("Transformer", "year", 2021, 12),
            _make_record("Attention", "year", 2021, 3),
        ]
        repo = Neo4jMethodTrendRepository(driver)
        result = repo.get_yearly_usage_counts(["Transformer", "Attention"], 2020, 2021)
        assert result == {
            "Transformer": {2020: 5, 2021: 12},
            "Attention": {2021: 3},
        }

    def test_empty_method_names_skips_query(self):
        driver, session = _make_driver()
        repo = Neo4jMethodTrendRepository(driver)
        result = repo.get_yearly_usage_counts([], 2019, 2023)
        assert result == {}
        session.run.assert_not_called()

    def test_invalid_year_range_raises(self):
        driver, _ = _make_driver()
        repo = Neo4jMethodTrendRepository(driver)
        with pytest.raises(ValueError):
            repo.get_yearly_usage_counts(["A"], 2023, 2019)


# ---------------------------------------------------------------------------
# get_venue_distribution
# ---------------------------------------------------------------------------

class TestGetVenueDistribution:
    def test_sends_correct_cypher(self):
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jMethodTrendRepository(driver)
        repo.get_venue_distribution(["BERT"], 2018, 2022)
        session.run.assert_called_once_with(
            _VENUE_DISTRIBUTION,
            method_names=["BERT"],
            year_start=2018,
            year_end=2022,
        )

    def test_groups_results_by_method_and_venue(self):
        driver, session = _make_driver()
        session.run.return_value = [
            _make_record("BERT", "venue", "NeurIPS", 8),
            _make_record("BERT", "venue", "ICML", 4),
            _make_record("GPT", "venue", "NeurIPS", 2),
        ]
        repo = Neo4jMethodTrendRepository(driver)
        result = repo.get_venue_distribution(["BERT", "GPT"], 2018, 2022)
        assert result == {
            "BERT": {"NeurIPS": 8, "ICML": 4},
            "GPT": {"NeurIPS": 2},
        }

    def test_empty_method_names_skips_query(self):
        driver, session = _make_driver()
        repo = Neo4jMethodTrendRepository(driver)
        result = repo.get_venue_distribution([], 2019, 2023)
        assert result == {}
        session.run.assert_not_called()


# ---------------------------------------------------------------------------
# get_all_yearly_usage_counts  (Discovery mode — no name filter)
# ---------------------------------------------------------------------------

class TestGetAllYearlyUsageCounts:
    def test_sends_correct_cypher_without_name_filter(self):
        """_ALL_YEARLY_USAGE must be used (not _YEARLY_USAGE) and no method_names param."""
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jMethodTrendRepository(driver)
        repo.get_all_yearly_usage_counts(2019, 2023)
        session.run.assert_called_once_with(
            _ALL_YEARLY_USAGE,
            year_start=2019,
            year_end=2023,
        )

    def test_does_not_use_filtered_cypher(self):
        """Must NOT call _YEARLY_USAGE (which requires method_names param)."""
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jMethodTrendRepository(driver)
        repo.get_all_yearly_usage_counts(2019, 2023)
        actual_cypher = session.run.call_args[0][0]
        assert actual_cypher is _ALL_YEARLY_USAGE
        assert actual_cypher is not _YEARLY_USAGE

    def test_groups_all_methods(self):
        driver, session = _make_driver()
        session.run.return_value = [
            _make_record("MethodA", "year", 2020, 3),
            _make_record("MethodB", "year", 2020, 7),
            _make_record("MethodA", "year", 2021, 9),
        ]
        repo = Neo4jMethodTrendRepository(driver)
        result = repo.get_all_yearly_usage_counts(2020, 2021)
        assert result == {
            "MethodA": {2020: 3, 2021: 9},
            "MethodB": {2020: 7},
        }

    def test_invalid_year_range_raises(self):
        driver, _ = _make_driver()
        repo = Neo4jMethodTrendRepository(driver)
        with pytest.raises(ValueError):
            repo.get_all_yearly_usage_counts(2023, 2019)

    def test_empty_graph_returns_empty_dict(self):
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jMethodTrendRepository(driver)
        result = repo.get_all_yearly_usage_counts(2019, 2023)
        assert result == {}


# ---------------------------------------------------------------------------
# get_all_venue_distributions  (Discovery mode — no name filter)
# ---------------------------------------------------------------------------

class TestGetAllVenueDistributions:
    def test_sends_correct_cypher_without_name_filter(self):
        """_ALL_VENUE_DISTRIBUTION must be used (not _VENUE_DISTRIBUTION)."""
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jMethodTrendRepository(driver)
        repo.get_all_venue_distributions(2019, 2023)
        session.run.assert_called_once_with(
            _ALL_VENUE_DISTRIBUTION,
            year_start=2019,
            year_end=2023,
        )

    def test_does_not_use_filtered_cypher(self):
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jMethodTrendRepository(driver)
        repo.get_all_venue_distributions(2019, 2023)
        actual_cypher = session.run.call_args[0][0]
        assert actual_cypher is _ALL_VENUE_DISTRIBUTION
        assert actual_cypher is not _VENUE_DISTRIBUTION

    def test_groups_all_methods_by_venue(self):
        driver, session = _make_driver()
        session.run.return_value = [
            _make_record("MethodA", "venue", "ICML", 5),
            _make_record("MethodA", "venue", "NeurIPS", 3),
            _make_record("MethodB", "venue", "ICLR", 10),
        ]
        repo = Neo4jMethodTrendRepository(driver)
        result = repo.get_all_venue_distributions(2019, 2023)
        assert result == {
            "MethodA": {"ICML": 5, "NeurIPS": 3},
            "MethodB": {"ICLR": 10},
        }

    def test_invalid_year_range_raises(self):
        driver, _ = _make_driver()
        repo = Neo4jMethodTrendRepository(driver)
        with pytest.raises(ValueError):
            repo.get_all_venue_distributions(2025, 2020)

    def test_empty_graph_returns_empty_dict(self):
        driver, session = _make_driver()
        session.run.return_value = []
        repo = Neo4jMethodTrendRepository(driver)
        result = repo.get_all_venue_distributions(2019, 2023)
        assert result == {}
