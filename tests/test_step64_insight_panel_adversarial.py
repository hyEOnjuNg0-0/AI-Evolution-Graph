"""
Adversarial test suite for Step 6.4 Insight Panel (Frontend + Backend Integration).
"""

import pytest
from pydantic import ValidationError
from aievograph.domain.ports.citation_time_series_repository import (
    CitationTimeSeriesRepositoryPort,
)
from aievograph.domain.ports.method_trend_repository import MethodTrendRepositoryPort
from aievograph.domain.services.breakthrough_detection_service import (
    BreakthroughDetectionService,
)
from aievograph.domain.services.trend_momentum_service import TrendMomentumService
from aievograph.api.schemas.breakthrough import (
    BreakthroughRequest,
    BreakthroughCandidate,
    BreakthroughResponse,
)
from aievograph.api.schemas.trend import TrendRequest, TrendResponse


class MockTimeSeriesRepo(CitationTimeSeriesRepositoryPort):
    def __init__(self, data=None):
        self._data = data or {}

    def get_yearly_citation_counts(self, paper_ids, year_start, year_end):
        return self._data


class MockMethodTrendRepo(MethodTrendRepositoryPort):
    def __init__(self, usage=None, venues=None):
        self._usage = usage or {}
        self._venues = venues or {}

    def get_yearly_usage_counts(self, method_names, year_start, year_end):
        return self._usage

    def get_venue_distribution(self, method_names, year_start, year_end):
        return self._venues

    def get_all_yearly_usage_counts(self, year_start, year_end):
        return self._usage

    def get_all_venue_distributions(self, year_start, year_end):
        return self._venues


class TestBreakthroughEdgeCases:
    def test_empty_field_string_rejected(self):
        """E-1 fix: Empty field must be rejected by validate_not_blank."""
        with pytest.raises(ValidationError, match="field must not be blank"):
            BreakthroughRequest(field="", start_year=2020, end_year=2025, top_k=10)

    def test_zero_top_k_rejected(self):
        with pytest.raises(ValueError):
            BreakthroughRequest(field="test", start_year=2020, end_year=2025, top_k=0)

    def test_service_empty_paper_ids(self):
        repo = MockTimeSeriesRepo({})
        svc = BreakthroughDetectionService(repo)
        result = svc.detect(paper_ids=[], year_start=2020, year_end=2025, top_k=10)
        assert result == []

    def test_service_all_zero_citations(self):
        repo = MockTimeSeriesRepo({"p1": {2020: 0, 2021: 0}})
        svc = BreakthroughDetectionService(repo)
        result = svc.detect(["p1"], 2020, 2021, 10)
        assert len(result) == 1
        assert result[0].burst_score == 0.0


class TestTrendMomentumEdgeCases:
    def test_empty_methods(self):
        repo = MockMethodTrendRepo({}, {})
        svc = TrendMomentumService(repo)
        result = svc.score([], 2024, 5, 10)
        assert result == []

    def test_zero_usage_methods(self):
        repo = MockMethodTrendRepo(
            usage={"m1": {2020: 0, 2021: 0}},
            venues={"m1": {}}
        )
        svc = TrendMomentumService(repo)
        result = svc.score(["m1"], 2021, 2, 10)
        assert len(result) == 1
        assert result[0].cagr_score == 0.0


class TestBreakthroughRequestSchema:
    def test_top_k_defaults(self):
        req = BreakthroughRequest(field="test", start_year=2020, end_year=2025)
        assert req.top_k == 10


class TestBreakthroughResponseIntegrity:
    def test_year_nullable(self):
        c = BreakthroughCandidate(
            paper_id="p1", title="Test", year=None,
            burst_score=0.5, centrality_shift=0.3, composite_score=0.4
        )
        assert c.year is None

    def test_empty_response(self):
        resp = BreakthroughResponse(candidates=[], total=0)
        assert resp.candidates == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
