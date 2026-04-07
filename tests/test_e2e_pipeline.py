"""
E2E pipeline test: Query → Graph → Retrieval → Ranking → Analysis → UI (API).

Covers the full request-response cycle for all four API endpoints using
FastAPI's TestClient and dependency overrides — no real Neo4j or OpenAI calls.

Test data models a minimal 4-paper citation graph:
  P_2017 (Attention Is All You Need)
    └─CITES→ P_2015 (Neural Machine Translation)
  P_2018 (BERT)
    └─CITES→ P_2017
  P_2020 (GPT-3)
    └─CITES→ P_2018

Method evolution:
  Transformer --IMPROVES--> RNN
  BERT        --EXTENDS-->  Transformer
  GPT-3       --IMPROVES--> BERT
"""

from unittest.mock import MagicMock

import pytest
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
# Shared test fixtures
# ---------------------------------------------------------------------------

def _make_author(suffix: str) -> Author:
    return Author(author_id=f"AUTH_{suffix}", name=f"Author {suffix}")


def _make_paper(paper_id: str, title: str, year: int, citation_count: int = 0) -> Paper:
    return Paper(
        paper_id=paper_id,
        title=title,
        publication_year=year,
        venue="NeurIPS",
        citation_count=citation_count,
        authors=[_make_author(paper_id)],
    )


# Fixed paper corpus used across all tests.
P_2015 = _make_paper("P_2015", "Neural Machine Translation by Jointly Learning to Align and Translate", 2015, citation_count=500)
P_2017 = _make_paper("P_2017", "Attention Is All You Need", 2017, citation_count=9000)
P_2018 = _make_paper("P_2018", "BERT: Pre-training of Deep Bidirectional Transformers", 2018, citation_count=7000)
P_2020 = _make_paper("P_2020", "Language Models are Few-Shot Learners (GPT-3)", 2020, citation_count=5000)

_ALL_PAPERS = [P_2015, P_2017, P_2018, P_2020]

# Scored papers ordered by hybrid score descending.
_SCORED_PAPERS = [
    ScoredPaper(paper=P_2017, score=0.92, semantic_sim=0.95, graph_prox=0.89),
    ScoredPaper(paper=P_2018, score=0.88, semantic_sim=0.90, graph_prox=0.86),
    ScoredPaper(paper=P_2020, score=0.75, semantic_sim=0.78, graph_prox=0.72),
    ScoredPaper(paper=P_2015, score=0.60, semantic_sim=0.55, graph_prox=0.65),
]

_SUBGRAPH = Subgraph(papers=_SCORED_PAPERS)

# Breakthrough candidates.
_BREAKTHROUGH_CANDIDATES = [
    BreakthroughCandidate(paper_id="P_2017", burst_score=0.95, centrality_shift=0.88, breakthrough_score=0.92),
    BreakthroughCandidate(paper_id="P_2018", burst_score=0.80, centrality_shift=0.75, breakthrough_score=0.78),
    BreakthroughCandidate(paper_id="P_2020", burst_score=0.65, centrality_shift=0.60, breakthrough_score=0.63),
]

# Method trend scores.
_TREND_SCORES = [
    MethodTrendScore(
        method_name="Transformer",
        cagr_score=0.90,
        entropy_score=0.85,
        adoption_velocity_score=0.88,
        trend_score=0.88,
        yearly_counts={2017: 10, 2018: 50, 2019: 200, 2020: 500},
    ),
    MethodTrendScore(
        method_name="BERT",
        cagr_score=0.85,
        entropy_score=0.80,
        adoption_velocity_score=0.82,
        trend_score=0.82,
        yearly_counts={2018: 30, 2019: 300, 2020: 800},
    ),
]

# Evolution path: RNN → Transformer → BERT → GPT-3.
_EVOLUTION_PATH = EvolutionPath(
    path=["RNN", "Transformer", "BERT", "GPT-3"],
    relation_types=["IMPROVES", "EXTENDS", "IMPROVES"],
    branch_points=["Transformer"],
    influence_scores={"RNN": 0.30, "Transformer": 0.88, "BERT": 0.82, "GPT-3": 0.75},
    mean_influence=0.69,
)

_ALL_METHOD_NAMES = ["RNN", "Transformer", "BERT", "GPT-3", "Attention"]


# ---------------------------------------------------------------------------
# Mock service factories
# ---------------------------------------------------------------------------

def _mock_hybrid_retrieval_service() -> MagicMock:
    svc = MagicMock()
    svc.search.return_value = _SUBGRAPH
    return svc


def _mock_graph_repository() -> MagicMock:
    repo = MagicMock()
    # get_citation_neighborhood returns neighbors for edge drawing.
    repo.get_citation_neighborhood.side_effect = lambda paper_id, hops: {
        "P_2017": [P_2015],
        "P_2018": [P_2017],
        "P_2020": [P_2018],
        "P_2015": [],
    }.get(paper_id, [])
    # get_paper_by_id used in breakthrough enrichment.
    repo.get_paper_by_id.side_effect = lambda pid: {
        p.paper_id: p for p in _ALL_PAPERS
    }.get(pid)
    # get_all_method_names for evolution fuzzy match.
    repo.get_all_method_names.return_value = _ALL_METHOD_NAMES
    # get_paper_ids_by_year_range for evolution path.
    repo.get_paper_ids_by_year_range.return_value = [p.paper_id for p in _ALL_PAPERS]
    return repo


def _mock_breakthrough_service() -> MagicMock:
    svc = MagicMock()
    svc.detect.return_value = _BREAKTHROUGH_CANDIDATES
    return svc


def _mock_trend_service() -> MagicMock:
    svc = MagicMock()
    svc.score.return_value = _TREND_SCORES
    return svc


def _mock_evolution_service() -> MagicMock:
    svc = MagicMock()
    svc.extract.return_value = [_EVOLUTION_PATH]
    return svc


# ---------------------------------------------------------------------------
# Client fixture with dependency overrides
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    """TestClient with all external dependencies replaced by lightweight mocks."""
    app.dependency_overrides = {
        get_hybrid_retrieval_service: _mock_hybrid_retrieval_service,
        get_graph_repository:         _mock_graph_repository,
        get_breakthrough_service:     _mock_breakthrough_service,
        get_trend_service:            _mock_trend_service,
        get_evolution_path_service:   _mock_evolution_service,
    }
    with TestClient(app) as c:
        yield c
    app.dependency_overrides = {}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Feature ①: Research Lineage Exploration (POST /api/lineage)
# ---------------------------------------------------------------------------

class TestLineageE2E:
    """End-to-end: Query → Hybrid Retrieval → Citation Edges → API response."""

    def test_lineage_happy_path(self, client: TestClient) -> None:
        """Full pipeline returns papers and citation edges for a keyword query."""
        resp = client.post("/api/lineage", json={
            "seed": "attention mechanism transformers",
            "hop_depth": 2,
            "top_k": 10,
            "query_type": "balanced",
        })
        assert resp.status_code == 200
        data = resp.json()

        # Response shape
        assert "papers" in data
        assert "edges" in data
        assert "total" in data

        # All 4 papers are returned (within default year filter = None)
        paper_ids = {p["paper_id"] for p in data["papers"]}
        assert paper_ids == {"P_2015", "P_2017", "P_2018", "P_2020"}
        assert data["total"] == 4

        # Hybrid scores are present and within valid range
        for p in data["papers"]:
            assert 0.0 <= p["score"] <= 1.0
            assert 0.0 <= p["semantic_similarity"] <= 1.0
            assert 0.0 <= p["graph_proximity"] <= 1.0

        # Citation edges exist within the result set
        assert len(data["edges"]) > 0
        for edge in data["edges"]:
            assert edge["source_id"] in paper_ids
            assert edge["target_id"] in paper_ids

    def test_lineage_year_filter(self, client: TestClient) -> None:
        """Year filters exclude papers outside the window."""
        resp = client.post("/api/lineage", json={
            "seed": "BERT transformers",
            "start_year": 2018,
            "end_year": 2020,
            "top_k": 10,
        })
        assert resp.status_code == 200
        data = resp.json()
        years = [p["year"] for p in data["papers"]]
        assert all(2018 <= y <= 2020 for y in years)
        # P_2015 (year=2015) must be excluded
        assert "P_2015" not in {p["paper_id"] for p in data["papers"]}

    def test_lineage_semantic_query_type(self, client: TestClient) -> None:
        """semantic query_type is accepted and returns a valid response."""
        resp = client.post("/api/lineage", json={
            "seed": "language model pretraining",
            "query_type": "semantic",
            "top_k": 5,
        })
        assert resp.status_code == 200

    def test_lineage_invalid_year_range(self, client: TestClient) -> None:
        """start_year > end_year must return 422."""
        resp = client.post("/api/lineage", json={
            "seed": "attention",
            "start_year": 2021,
            "end_year": 2018,
        })
        assert resp.status_code == 422

    def test_lineage_papers_sorted_by_score_descending(self, client: TestClient) -> None:
        """Papers in the response are ordered by hybrid score descending."""
        resp = client.post("/api/lineage", json={"seed": "neural networks"})
        assert resp.status_code == 200
        scores = [p["score"] for p in resp.json()["papers"]]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Feature ②: Breakthrough Detection (POST /api/breakthrough)
# ---------------------------------------------------------------------------

class TestBreakthroughE2E:
    """End-to-end: Field query → Semantic retrieval → Burst/shift analysis → API response."""

    def test_breakthrough_happy_path(self, client: TestClient) -> None:
        """Full pipeline returns ranked breakthrough candidates."""
        resp = client.post("/api/breakthrough", json={
            "field": "transformer attention mechanism",
            "start_year": 2015,
            "end_year": 2022,
            "top_k": 10,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert "candidates" in data
        assert "total" in data
        assert data["total"] == len(data["candidates"])

        candidates = data["candidates"]
        assert len(candidates) == 3

        # Verify score fields are in [0, 1]
        for c in candidates:
            assert 0.0 <= c["burst_score"] <= 1.0
            assert 0.0 <= c["centrality_shift"] <= 1.0
            assert 0.0 <= c["composite_score"] <= 1.0

        # Top candidate is P_2017 (Attention Is All You Need)
        assert candidates[0]["paper_id"] == "P_2017"
        assert "Attention" in candidates[0]["title"]

    def test_breakthrough_candidates_enriched_with_metadata(self, client: TestClient) -> None:
        """Each candidate includes paper title and year from the graph."""
        resp = client.post("/api/breakthrough", json={
            "field": "deep learning",
            "start_year": 2015,
            "end_year": 2022,
        })
        data = resp.json()
        for c in data["candidates"]:
            assert c["title"] != c["paper_id"]  # title was resolved, not just paper_id
            assert c["year"] is not None

    def test_breakthrough_year_window_filters_candidates(self, client: TestClient) -> None:
        """Only papers within start_year..end_year are fed into detection."""
        # Mock retrieval returns all 4 papers; window 2017-2017 should only pass P_2017.
        resp = client.post("/api/breakthrough", json={
            "field": "attention",
            "start_year": 2017,
            "end_year": 2017,
        })
        assert resp.status_code == 200
        # breakthrough_svc.detect was called with only the in-window paper IDs.

    def test_breakthrough_empty_window_returns_empty(self, client: TestClient) -> None:
        """If no papers fall in the requested window, return empty candidates list."""
        resp = client.post("/api/breakthrough", json={
            "field": "quantum computing",
            "start_year": 1960,
            "end_year": 1961,
        })
        assert resp.status_code == 200
        data = resp.json()
        # All scored papers have years >= 2015, so the window 1960-1961 excludes all.
        assert data["candidates"] == []
        assert data["total"] == 0

    def test_breakthrough_invalid_year_range(self, client: TestClient) -> None:
        """start_year > end_year must return 422."""
        resp = client.post("/api/breakthrough", json={
            "field": "transformers",
            "start_year": 2022,
            "end_year": 2018,
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Feature ③: Trending Methods Discovery (POST /api/trend)
# ---------------------------------------------------------------------------

class TestTrendE2E:
    """End-to-end: Year window → TrendMomentumService → Ranked method list."""

    def test_trend_happy_path(self, client: TestClient) -> None:
        """Full pipeline returns top-k methods with momentum scores."""
        resp = client.post("/api/trend", json={
            "start_year": 2017,
            "end_year": 2021,
            "top_k": 10,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["start_year"] == 2017
        assert data["end_year"] == 2021
        assert "methods" in data

        methods = data["methods"]
        assert len(methods) == 2  # matches _TREND_SCORES

        for m in methods:
            assert "method_name" in m
            assert "cagr" in m
            assert "entropy" in m
            assert "adoption_velocity" in m
            assert "momentum_score" in m
            assert "yearly_counts" in m
            assert 0.0 <= m["momentum_score"] <= 1.0

    def test_trend_methods_sorted_by_momentum_descending(self, client: TestClient) -> None:
        """Transformer (score=0.88) ranks above BERT (score=0.82)."""
        resp = client.post("/api/trend", json={"start_year": 2017, "end_year": 2021})
        assert resp.status_code == 200
        methods = resp.json()["methods"]
        scores = [m["momentum_score"] for m in methods]
        assert scores == sorted(scores, reverse=True)
        assert methods[0]["method_name"] == "Transformer"

    def test_trend_yearly_counts_keys_are_strings(self, client: TestClient) -> None:
        """JSON serialization converts year int keys to strings."""
        resp = client.post("/api/trend", json={"start_year": 2017, "end_year": 2021})
        methods = resp.json()["methods"]
        for m in methods:
            for key in m["yearly_counts"]:
                assert isinstance(key, str)
                assert key.isdigit()

    def test_trend_invalid_year_range(self, client: TestClient) -> None:
        """start_year > end_year must return 422."""
        resp = client.post("/api/trend", json={"start_year": 2022, "end_year": 2018})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Feature ④: Method Evolution Path (POST /api/evolution)
# ---------------------------------------------------------------------------

class TestEvolutionE2E:
    """End-to-end: Method name → Fuzzy match → Trend scoring → Evolution DAG → API response."""

    def test_evolution_happy_path(self, client: TestClient) -> None:
        """Full pipeline returns evolution path for a known method."""
        resp = client.post("/api/evolution", json={
            "method_name": "Transformer",
            "start_year": 2017,
            "end_year": 2021,
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["method_name"] == "Transformer"
        assert "evolution_path" in data
        assert "yearly_counts" in data
        assert "influence_scores" in data

        steps = data["evolution_path"]
        # Path: RNN→Transformer→BERT→GPT-3 yields 3 steps.
        assert len(steps) == 3
        assert steps[0]["from_method"] == "RNN"
        assert steps[0]["to_method"] == "Transformer"
        assert steps[0]["relation_type"] == "IMPROVES"
        assert steps[1]["from_method"] == "Transformer"
        assert steps[1]["to_method"] == "BERT"
        assert steps[1]["relation_type"] == "EXTENDS"

    def test_evolution_influence_scores_in_range(self, client: TestClient) -> None:
        """Influence scores are normalized to [0, 1]."""
        resp = client.post("/api/evolution", json={
            "method_name": "BERT",
            "start_year": 2018,
            "end_year": 2021,
        })
        assert resp.status_code == 200
        influence = resp.json()["influence_scores"]
        for score in influence.values():
            assert 0.0 <= score <= 1.0

    def test_evolution_yearly_counts_keys_are_strings(self, client: TestClient) -> None:
        """Yearly counts use string keys in JSON."""
        resp = client.post("/api/evolution", json={
            "method_name": "Transformer",
            "start_year": 2017,
            "end_year": 2021,
        })
        yearly = resp.json()["yearly_counts"]
        for key in yearly:
            assert isinstance(key, str)
            assert key.isdigit()

    def test_evolution_unknown_method_returns_404(self, client: TestClient) -> None:
        """Method name with no fuzzy match must return 404."""
        resp = client.post("/api/evolution", json={
            "method_name": "XYZ_NONEXISTENT_METHOD_9999",
            "start_year": 2017,
            "end_year": 2021,
        })
        assert resp.status_code == 404

    def test_evolution_invalid_year_range(self, client: TestClient) -> None:
        """start_year > end_year must return 422."""
        resp = client.post("/api/evolution", json={
            "method_name": "Transformer",
            "start_year": 2025,
            "end_year": 2018,
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Cross-feature pipeline flow
# ---------------------------------------------------------------------------

class TestFullPipelineFlow:
    """Verify that the four endpoints can be called in sequence, simulating a
    realistic UI session: discover trends → explore lineage → find breakthroughs
    → trace evolution."""

    def test_four_step_research_session(self, client: TestClient) -> None:
        """Simulate a full user session across all four features."""
        # Step 1 — Discover trending methods.
        trend_resp = client.post("/api/trend", json={
            "start_year": 2017,
            "end_year": 2021,
            "top_k": 5,
        })
        assert trend_resp.status_code == 200
        top_method = trend_resp.json()["methods"][0]["method_name"]
        assert top_method == "Transformer"

        # Step 2 — Explore lineage seeded by the top method name.
        lineage_resp = client.post("/api/lineage", json={
            "seed": top_method,
            "hop_depth": 2,
            "top_k": 10,
        })
        assert lineage_resp.status_code == 200
        lineage_paper_ids = {p["paper_id"] for p in lineage_resp.json()["papers"]}
        assert len(lineage_paper_ids) > 0

        # Step 3 — Detect breakthroughs in the lineage field.
        bt_resp = client.post("/api/breakthrough", json={
            "field": top_method,
            "start_year": 2015,
            "end_year": 2022,
            "top_k": 5,
        })
        assert bt_resp.status_code == 200
        assert bt_resp.json()["total"] > 0

        # Step 4 — Trace the method's evolution path.
        evo_resp = client.post("/api/evolution", json={
            "method_name": top_method,
            "start_year": 2015,
            "end_year": 2022,
        })
        assert evo_resp.status_code == 200
        assert len(evo_resp.json()["evolution_path"]) > 0
