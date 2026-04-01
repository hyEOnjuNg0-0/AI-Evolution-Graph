"""
Adversarial Tests for Phase 6 Step 6.2 — FastAPI Layer (Layer E)
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aievograph.api.main import app
from aievograph.api.schemas.lineage import LineageRequest
from aievograph.api.schemas.breakthrough import BreakthroughRequest
from aievograph.api.schemas.trend import TrendRequest
from aievograph.domain.models import Paper, ScoredPaper, Subgraph, Author


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


def _make_paper(paper_id: str, year: int = 2020):
    """Helper to construct a Paper domain model."""
    return Paper(
        paper_id=paper_id,
        title=f"Title {paper_id}",
        publication_year=year,
        citation_count=10,
        authors=[Author(author_id="a1", name="Author 1")]
    )


def _make_scored_paper(paper_id: str, score: float = 0.5):
    """Helper to construct a ScoredPaper."""
    return ScoredPaper(paper=_make_paper(paper_id), score=score)


# C-1 fix: Year range reversal is now caught at schema level.

class TestYearRangeReversal:
    """Reversed year ranges must be rejected by Pydantic before reaching route handlers."""

    def test_lineage_year_range_reversal_rejected(self):
        """Lineage: start_year > end_year raises ValidationError."""
        with pytest.raises(ValidationError, match="start_year must be <= end_year"):
            LineageRequest(seed="test", start_year=2024, end_year=2020)

    def test_breakthrough_year_range_reversal_rejected(self):
        """Breakthrough: start_year > end_year raises ValidationError."""
        with pytest.raises(ValidationError, match="start_year must be <= end_year"):
            BreakthroughRequest(field="test", start_year=2024, end_year=2020)

    def test_trend_year_range_reversal_rejected(self):
        """Trend: start_year > end_year raises ValidationError."""
        with pytest.raises(ValidationError, match="start_year must be <= end_year"):
            TrendRequest(topic="test", start_year=2024, end_year=2020)


class TestLineageEndpoint:
    """Test /api/lineage endpoint."""

    def test_health_endpoint_works(self, client):
        """Smoke test: /health should always work."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
