"""
Router-level tests for the three FastAPI endpoints.

Each test overrides FastAPI dependency injection with a lightweight stub so that
no real Neo4j connection or OpenAI call is made.
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from aievograph.api.main import app
from aievograph.api.dependencies import (
    get_breakthrough_service,
    get_evolution_path_service,
    get_graph_repository,
    get_hybrid_retrieval_service,
    get_trend_service,
)
from aievograph.domain.models import (
    Author,
    BreakthroughCandidate,
    EvolutionPath,
    MethodTrendScore,
    Paper,
    ScoredPaper,
    Subgraph,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _paper(paper_id: str, year: int = 2020) -> Paper:
    return Paper(
        paper_id=paper_id,
        title=f"Title {paper_id}",
        publication_year=year,
        citation_count=5,
        authors=[Author(author_id="a1", name="Author A")],
    )


def _scored(paper_id: str, score: float = 0.7, year: int = 2020) -> ScoredPaper:
    return ScoredPaper(paper=_paper(paper_id, year), score=score)


# ---------------------------------------------------------------------------
# /api/lineage
# ---------------------------------------------------------------------------

class TestLineageRouter:

    @pytest.fixture
    def client(self):
        retrieval = MagicMock()
        retrieval.search.return_value = Subgraph(papers=[
            _scored("p1", 0.9, 2021),
            _scored("p2", 0.6, 2019),
        ])

        graph = MagicMock()
        graph.get_citation_neighborhood.return_value = []

        app.dependency_overrides[get_hybrid_retrieval_service] = lambda: retrieval
        app.dependency_overrides[get_graph_repository] = lambda: graph
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_returns_papers_and_edges(self, client):
        resp = client.post("/api/lineage", json={"seed": "transformer"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["papers"]) == 2
        assert isinstance(body["edges"], list)

    def test_year_filter_excludes_out_of_range(self, client):
        """start_year=2020 should exclude the paper from 2019."""
        resp = client.post("/api/lineage", json={
            "seed": "transformer",
            "start_year": 2020,
        })
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_reversed_year_range_returns_422(self, client):
        resp = client.post("/api/lineage", json={
            "seed": "transformer",
            "start_year": 2024,
            "end_year": 2020,
        })
        assert resp.status_code == 422

    def test_missing_seed_returns_422(self, client):
        resp = client.post("/api/lineage", json={})
        assert resp.status_code == 422

    def test_hop_depth_out_of_range_returns_422(self, client):
        resp = client.post("/api/lineage", json={"seed": "x", "hop_depth": 0})
        assert resp.status_code == 422

    def test_retrieval_value_error_returns_422(self, client):
        """A ValueError raised by the retrieval service must surface as HTTP 422."""
        retrieval = MagicMock()
        retrieval.search.side_effect = ValueError("embedding failed")
        app.dependency_overrides[get_hybrid_retrieval_service] = lambda: retrieval
        resp = client.post("/api/lineage", json={"seed": "transformer"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/breakthrough
# ---------------------------------------------------------------------------

class TestBreakthroughRouter:

    @pytest.fixture
    def client(self):
        retrieval = MagicMock()
        retrieval.search.return_value = Subgraph(papers=[_scored("p1", 0.8, 2020)])

        breakthrough = MagicMock()
        breakthrough.detect.return_value = [
            BreakthroughCandidate(
                paper_id="p1",
                burst_score=0.8,
                centrality_shift=0.6,
                breakthrough_score=0.75,
            )
        ]

        graph = MagicMock()
        graph.get_paper_by_id.return_value = _paper("p1", 2020)

        app.dependency_overrides[get_hybrid_retrieval_service] = lambda: retrieval
        app.dependency_overrides[get_breakthrough_service] = lambda: breakthrough
        app.dependency_overrides[get_graph_repository] = lambda: graph
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_returns_candidates(self, client):
        resp = client.post("/api/breakthrough", json={
            "field": "attention",
            "start_year": 2018,
            "end_year": 2022,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["candidates"][0]["paper_id"] == "p1"

    def test_reversed_year_range_returns_422(self, client):
        resp = client.post("/api/breakthrough", json={
            "field": "attention",
            "start_year": 2025,
            "end_year": 2018,
        })
        assert resp.status_code == 422

    def test_missing_field_returns_422(self, client):
        resp = client.post("/api/breakthrough", json={
            "start_year": 2018,
            "end_year": 2022,
        })
        assert resp.status_code == 422

    def test_no_candidates_in_year_range_returns_empty(self, client):
        """Papers outside the requested window produce an empty response."""
        resp = client.post("/api/breakthrough", json={
            "field": "attention",
            "start_year": 2000,
            "end_year": 2005,
        })
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# /api/trend
# ---------------------------------------------------------------------------

class TestTrendRouter:

    @pytest.fixture
    def client(self):
        graph = MagicMock()
        graph.get_all_method_names.return_value = ["transformer", "attention"]
        graph.get_papers_by_year_range.return_value = [_paper("p1", 2020)]

        trend = MagicMock()
        trend.score.return_value = [
            MethodTrendScore(
                method_name="transformer",
                cagr_score=0.8,
                entropy_score=0.6,
                adoption_velocity_score=0.7,
                trend_score=0.72,
            )
        ]

        breakthrough = MagicMock()
        breakthrough.detect.return_value = []

        evolution = MagicMock()
        evolution.extract.return_value = []

        app.dependency_overrides[get_graph_repository] = lambda: graph
        app.dependency_overrides[get_trend_service] = lambda: trend
        app.dependency_overrides[get_breakthrough_service] = lambda: breakthrough
        app.dependency_overrides[get_evolution_path_service] = lambda: evolution
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_returns_trend_scores(self, client):
        resp = client.post("/api/trend", json={
            "start_year": 2018,
            "end_year": 2022,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["start_year"] == 2018
        assert body["end_year"] == 2022
        assert len(body["methods"]) == 1
        assert body["methods"][0]["method_name"] == "transformer"
        assert body["methods"][0]["momentum_score"] == pytest.approx(0.72)

    def test_reversed_year_range_returns_422(self, client):
        resp = client.post("/api/trend", json={
            "start_year": 2025,
            "end_year": 2018,
        })
        assert resp.status_code == 422

    def test_missing_required_year_returns_422(self, client):
        resp = client.post("/api/trend", json={"start_year": 2018})
        assert resp.status_code == 422

    def test_no_trend_data_returns_empty_methods(self, client):
        """When TrendMomentumService finds no results, endpoint returns 200 with empty list."""
        trend = MagicMock()
        trend.score.return_value = []
        app.dependency_overrides[get_trend_service] = lambda: trend
        resp = client.post("/api/trend", json={
            "start_year": 2018,
            "end_year": 2022,
        })
        assert resp.status_code == 200
        assert resp.json()["methods"] == []


# ---------------------------------------------------------------------------
# /api/evolution
# ---------------------------------------------------------------------------

class TestEvolutionRouter:

    @pytest.fixture
    def client(self):
        graph = MagicMock()
        graph.get_all_method_names.return_value = ["transformer", "attention", "bert"]
        graph.get_paper_ids_by_year_range.return_value = ["p1", "p2"]

        trend = MagicMock()
        trend.score.return_value = [
            MethodTrendScore(
                method_name="transformer",
                cagr_score=0.9,
                entropy_score=0.7,
                adoption_velocity_score=0.8,
                trend_score=0.82,
                yearly_counts={2019: 5, 2022: 20},
            )
        ]

        breakthrough = MagicMock()
        breakthrough.detect.return_value = []

        evolution = MagicMock()
        evolution.extract.return_value = [
            EvolutionPath(
                path=["attention", "transformer"],
                relation_types=["IMPROVES"],
                influence_scores={"attention": 0.6, "transformer": 1.0},
            )
        ]

        app.dependency_overrides[get_graph_repository] = lambda: graph
        app.dependency_overrides[get_trend_service] = lambda: trend
        app.dependency_overrides[get_breakthrough_service] = lambda: breakthrough
        app.dependency_overrides[get_evolution_path_service] = lambda: evolution
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_returns_evolution_response(self, client):
        resp = client.post("/api/evolution", json={
            "method_name": "transformer",
            "start_year": 2018,
            "end_year": 2022,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["method_name"] == "transformer"
        assert isinstance(body["evolution_path"], list)
        assert len(body["evolution_path"]) == 1
        assert body["evolution_path"][0]["from_method"] == "attention"
        assert body["evolution_path"][0]["to_method"] == "transformer"
        assert "influence_scores" in body

    def test_no_match_returns_404(self, client):
        resp = client.post("/api/evolution", json={
            "method_name": "unknown_xyz_999",
            "start_year": 2018,
            "end_year": 2022,
        })
        assert resp.status_code == 404

    def test_reversed_year_range_returns_422(self, client):
        resp = client.post("/api/evolution", json={
            "method_name": "transformer",
            "start_year": 2025,
            "end_year": 2018,
        })
        assert resp.status_code == 422

    def test_missing_method_name_returns_422(self, client):
        resp = client.post("/api/evolution", json={"start_year": 2018, "end_year": 2022})
        assert resp.status_code == 422

    def test_get_all_method_names_returns_none_does_not_crash(self, client):
        """None return from graph_repo.get_all_method_names() must not raise TypeError."""
        graph = MagicMock()
        graph.get_all_method_names.return_value = None
        app.dependency_overrides[get_graph_repository] = lambda: graph
        resp = client.post("/api/evolution", json={
            "method_name": "transformer",
            "start_year": 2018,
            "end_year": 2022,
        })
        assert resp.status_code == 404

    def test_no_paper_ids_returns_response_with_empty_path(self, client):
        """When no papers exist in the year range, evolution_path should be empty."""
        graph = MagicMock()
        graph.get_all_method_names.return_value = ["transformer"]
        graph.get_paper_ids_by_year_range.return_value = []

        trend = MagicMock()
        trend.score.return_value = [
            MethodTrendScore(
                method_name="transformer",
                cagr_score=0.5,
                entropy_score=0.5,
                adoption_velocity_score=0.5,
                trend_score=0.5,
            )
        ]

        app.dependency_overrides[get_graph_repository] = lambda: graph
        app.dependency_overrides[get_trend_service] = lambda: trend
        resp = client.post("/api/evolution", json={
            "method_name": "transformer",
            "start_year": 2018,
            "end_year": 2022,
        })
        assert resp.status_code == 200
        assert resp.json()["evolution_path"] == []
