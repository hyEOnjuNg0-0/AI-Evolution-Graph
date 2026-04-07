"""
Adversarial Tests for Phase 6 Step 6.2 — API Schema Layer Validation

CRITICAL VULNERABILITIES found in Pydantic schemas.
"""

import pytest
from pydantic import ValidationError

from aievograph.api.schemas.lineage import LineageRequest
from aievograph.api.schemas.breakthrough import BreakthroughRequest
from aievograph.api.schemas.trend import TrendRequest


class TestLineageRequestSchema:
    """Test LineageRequest Pydantic validation."""

    def test_seed_is_required(self):
        """Adversarial: Missing seed field should fail."""
        with pytest.raises(ValidationError, match="seed"):
            LineageRequest()

    def test_seed_empty_string_rejected(self):
        """E-1 fix: Empty seed must be rejected by validate_not_blank."""
        with pytest.raises(ValidationError, match="seed must not be blank"):
            LineageRequest(seed="")

    def test_hop_depth_minimum_one(self):
        """Adversarial: hop_depth < 1 should fail."""
        with pytest.raises(ValidationError):
            LineageRequest(seed="test", hop_depth=0)

    def test_hop_depth_maximum_five(self):
        """Adversarial: hop_depth > 5 should fail."""
        with pytest.raises(ValidationError):
            LineageRequest(seed="test", hop_depth=6)

    def test_top_k_maximum_one_hundred(self):
        """Adversarial: top_k > 100 should fail."""
        with pytest.raises(ValidationError):
            LineageRequest(seed="test", top_k=101)

    def test_query_type_invalid_rejected(self):
        """Adversarial: Invalid query_type should fail."""
        with pytest.raises(ValidationError):
            LineageRequest(seed="test", query_type="invalid")

    def test_year_range_reversed_raises_validation_error(self):
        """C-1 fix: start_year > end_year must be rejected at schema level."""
        with pytest.raises(ValidationError, match="start_year must be <= end_year"):
            LineageRequest(seed="test", start_year=2024, end_year=2020)

    def test_year_range_equal_is_valid(self):
        """start_year == end_year (single-year window) is allowed."""
        req = LineageRequest(seed="test", start_year=2020, end_year=2020)
        assert req.start_year == req.end_year == 2020

    def test_year_range_only_start_is_valid(self):
        """Providing only start_year (no end_year) must be valid."""
        req = LineageRequest(seed="test", start_year=2020)
        assert req.start_year == 2020
        assert req.end_year is None

    def test_year_range_only_end_is_valid(self):
        """Providing only end_year (no start_year) must be valid."""
        req = LineageRequest(seed="test", end_year=2022)
        assert req.end_year == 2022
        assert req.start_year is None


class TestBreakthroughRequestSchema:
    """Test BreakthroughRequest Pydantic validation."""

    def test_year_range_reversed_raises_validation_error(self):
        """C-1 fix: start_year > end_year must be rejected."""
        with pytest.raises(ValidationError, match="start_year must be <= end_year"):
            BreakthroughRequest(field="test", start_year=2024, end_year=2020)

    def test_year_range_equal_is_valid(self):
        """start_year == end_year is a valid single-year window."""
        req = BreakthroughRequest(field="test", start_year=2020, end_year=2020)
        assert req.start_year == req.end_year == 2020


class TestTrendRequestSchema:
    """Test TrendRequest Pydantic validation."""

    def test_year_range_reversed_raises_validation_error(self):
        """C-1 fix: start_year > end_year must be rejected."""
        with pytest.raises(ValidationError, match="start_year must be <= end_year"):
            TrendRequest(topic="test", start_year=2024, end_year=2020)

    def test_year_range_equal_is_valid(self):
        """start_year == end_year is a valid single-year window."""
        req = TrendRequest(topic="test", start_year=2020, end_year=2020)
        assert req.start_year == req.end_year == 2020


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
