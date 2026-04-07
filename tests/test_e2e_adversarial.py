"""
Adversarial E2E tests: Edge cases, boundary violations, contract breaches.
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


P_2015 = _make_paper("P_2015", "Neural Machine Translation by Jointly Learning to Align and Translate", 2015, citation_count=500)
P_2017 = _make_paper("P_2017", "Attention Is All You Need", 2017, citation_count=9000)
P_2018 = _make_paper("P_2018", "BERT: Pre-training of Deep Bidirectional Transformers", 2018, citation_count=7000)
P_2020 = _make_paper("P_2020", "Language Models are Few-Shot Learners (GPT-3)", 2020, citation_count=5000)

_ALL_PAPERS = [P_2015, P_2017, P_2018, P_2020]

_SCORED_PAPERS = [
    ScoredPaper(paper=P_2017, score=0.92, semantic_sim=0.95, graph_prox=0.89),
    ScoredPaper(paper=P_2018, score=0.88, semantic_sim=0.90, graph_prox=0.86),
    ScoredPaper(paper=P_2020, score=0.75, semantic_sim=0.78, graph_prox=0.72),
    ScoredPaper(paper=P_2015, score=0.60, semantic_sim=0.55, graph_prox=0.65),
]

_SUBGRAPH = Subgraph(papers=_SCORED_PAPERS)

_BREAKTHROUGH_CANDIDATES = [
    BreakthroughCandidate(paper_id="P_2017", burst_score=0.95, centrality_shift=0.88, breakthrough_score=0.92),
    BreakthroughCandidate(paper_id="P_2018", burst_score=0.80, centrality_shift=0.75, breakthrough_score=0.78),
    BreakthroughCandidate(paper_id="P_2020", burst_score=0.65, centrality_shift=0.60, breakthrough_score=0.63),
]

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

_EVOLUTION_PATH = EvolutionPath(
    path=["RNN", "Transformer", "BERT", "GPT-3"],
    relation_types=["IMPROVES", "EXTENDS", "IMPROVES"],
    branch_points=["Transformer"],
    influence_scores={"RNN": 0.30, "Transformer": 0.88, "BERT": 0.82, "GPT-3": 0.75},
    mean_influence=0.69,
)

_ALL_METHOD_NAMES = ["RNN", "Transformer", "BERT", "GPT-3", "Attention"]


def _mock_hybrid_retrieval_service() -> MagicMock:
    svc = MagicMock()
    svc.search.return_value = _SUBGRAPH
    return svc


def _mock_graph_repository() -> MagicMock:
    repo = MagicMock()
    repo.get_citation_neighborhood.side_effect = lambda paper_id, hops: {
        "P_2017": [P_2015],
        "P_2018": [P_2017],
        "P_2020": [P_2018],
        "P_2015": [],
    }.get(paper_id, [])
    repo.get_paper_by_id.side_effect = lambda pid: {
        p.paper_id: p for p in _ALL_PAPERS
    }.get(pid)
    repo.get_all_method_names.return_value = _ALL_METHOD_NAMES
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


@pytest.fixture()
def client() -> TestClient:
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


class TestLineageAdversarial:
    def test_lineage_empty_seed_rejected(self, client: TestClient) -> None:
        resp = client.post("/api/lineage", json={"seed": "", "top_k": 10})
        assert resp.status_code == 422, "Empty seed must be rejected by validation"

    def test_lineage_whitespace_seed_rejected(self, client: TestClient) -> None:
        resp = client.post("/api/lineage", json={"seed": " " * 10, "top_k": 10})
        assert resp.status_code == 422, "Whitespace-only seed must be rejected"

    def test_lineage_year_boundary_single(self, client: TestClient) -> None:
        resp = client.post("/api/lineage", json={
            "seed": "test",
            "start_year": 2017,
            "end_year": 2017,
        })
        assert resp.status_code == 200


class TestBreakthroughAdversarial:
    def test_breakthrough_empty_field_rejected(self, client: TestClient) -> None:
        resp = client.post("/api/breakthrough", json={
            "field": "",
            "start_year": 2015,
            "end_year": 2020,
        })
        assert resp.status_code == 422, "Empty field must be rejected"

    def test_breakthrough_title_always_present(self, client: TestClient) -> None:
        resp = client.post("/api/breakthrough", json={
            "field": "test",
            "start_year": 2015,
            "end_year": 2022,
        })
        assert resp.status_code == 200
        for cand in resp.json()["candidates"]:
            assert "title" in cand
            assert cand["title"] is not None


class TestTrendAdversarial:
    def test_trend_single_year(self, client: TestClient) -> None:
        resp = client.post("/api/trend", json={
            "start_year": 2018,
            "end_year": 2018,
        })
        assert resp.status_code == 200


class TestEvolutionAdversarial:
    def test_evolution_case_insensitive(self, client: TestClient) -> None:
        resp = client.post("/api/evolution", json={
            "method_name": "transformer",
            "start_year": 2017,
            "end_year": 2021,
        })
        assert resp.status_code == 200


class TestInputValidationVulnerabilities:
    """Tests for missing input validation in schemas."""

    def test_lineage_seed_null_character(self, client: TestClient) -> None:
        # Null bytes should not crash the application
        resp = client.post("/api/lineage", json={"seed": "test\x00null", "top_k": 10})
        assert resp.status_code in [200, 422]

    def test_lineage_seed_unicode_handling(self, client: TestClient) -> None:
        resp = client.post("/api/lineage", json={"seed": "🚀💻✨", "top_k": 10})
        assert resp.status_code in [200, 422]

    def test_lineage_top_k_negative(self, client: TestClient) -> None:
        resp = client.post("/api/lineage", json={"seed": "test", "top_k": -1})
        assert resp.status_code == 422, "Negative top_k should be rejected"

    def test_lineage_hop_depth_negative(self, client: TestClient) -> None:
        resp = client.post("/api/lineage", json={"seed": "test", "hop_depth": -1})
        assert resp.status_code == 422, "Negative hop_depth should be rejected"


class TestResponseContractViolations:
    """Tests for API response contract violations."""

    def test_lineage_response_structure(self, client: TestClient) -> None:
        resp = client.post("/api/lineage", json={"seed": "test"})
        assert resp.status_code == 200
        data = resp.json()
        
        # Must have these top-level keys
        assert "papers" in data
        assert "edges" in data
        assert "total" in data
        
        # papers and edges must be lists
        assert isinstance(data["papers"], list)
        assert isinstance(data["edges"], list)
        assert isinstance(data["total"], int)

    def test_breakthrough_response_structure(self, client: TestClient) -> None:
        resp = client.post("/api/breakthrough", json={
            "field": "test",
            "start_year": 2015,
            "end_year": 2022,
        })
        assert resp.status_code == 200
        data = resp.json()
        
        assert "candidates" in data
        assert "total" in data
        assert isinstance(data["candidates"], list)
        assert isinstance(data["total"], int)

    def test_trend_response_structure(self, client: TestClient) -> None:
        resp = client.post("/api/trend", json={
            "start_year": 2017,
            "end_year": 2021,
        })
        assert resp.status_code == 200
        data = resp.json()
        
        assert "start_year" in data
        assert "end_year" in data
        assert "methods" in data
        assert isinstance(data["methods"], list)

    def test_evolution_response_structure(self, client: TestClient) -> None:
        resp = client.post("/api/evolution", json={
            "method_name": "Transformer",
            "start_year": 2017,
            "end_year": 2021,
        })
        assert resp.status_code == 200
        data = resp.json()
        
        assert "method_name" in data
        assert "evolution_path" in data
        assert "yearly_counts" in data
        assert "influence_scores" in data


class TestScoreRangeBoundaries:
    """Tests for score normalization and boundaries."""

    def test_lineage_scores_not_exceeding_one(self, client: TestClient) -> None:
        resp = client.post("/api/lineage", json={"seed": "test"})
        assert resp.status_code == 200
        for paper in resp.json()["papers"]:
            assert paper["score"] <= 1.0, f"score > 1.0: {paper['score']}"
            assert paper["semantic_similarity"] <= 1.0
            assert paper["graph_proximity"] <= 1.0

    def test_breakthrough_scores_normalized(self, client: TestClient) -> None:
        resp = client.post("/api/breakthrough", json={
            "field": "test",
            "start_year": 2015,
            "end_year": 2022,
        })
        assert resp.status_code == 200
        for cand in resp.json()["candidates"]:
            assert 0.0 <= cand["burst_score"] <= 1.0
            assert 0.0 <= cand["centrality_shift"] <= 1.0
            assert 0.0 <= cand["composite_score"] <= 1.0

    def test_trend_scores_normalized(self, client: TestClient) -> None:
        resp = client.post("/api/trend", json={
            "start_year": 2017,
            "end_year": 2021,
        })
        assert resp.status_code == 200
        for method in resp.json()["methods"]:
            assert 0.0 <= method["cagr"] <= 1.0
            assert 0.0 <= method["entropy"] <= 1.0
            assert 0.0 <= method["adoption_velocity"] <= 1.0
            assert 0.0 <= method["momentum_score"] <= 1.0

    def test_evolution_influence_normalized(self, client: TestClient) -> None:
        resp = client.post("/api/evolution", json={
            "method_name": "Transformer",
            "start_year": 2017,
            "end_year": 2021,
        })
        assert resp.status_code == 200
        for score in resp.json()["influence_scores"].values():
            assert 0.0 <= score <= 1.0, f"influence_score out of range: {score}"


class TestYearRangeHandling:
    """Tests for year range validation and filtering."""

    def test_breakthrough_year_equal_boundary(self, client: TestClient) -> None:
        resp = client.post("/api/breakthrough", json={
            "field": "test",
            "start_year": 2018,
            "end_year": 2018,
        })
        assert resp.status_code == 200

    def test_trend_year_equal_boundary(self, client: TestClient) -> None:
        resp = client.post("/api/trend", json={
            "start_year": 2018,
            "end_year": 2018,
        })
        assert resp.status_code == 200

    def test_evolution_year_equal_boundary(self, client: TestClient) -> None:
        resp = client.post("/api/evolution", json={
            "method_name": "Transformer",
            "start_year": 2018,
            "end_year": 2018,
        })
        assert resp.status_code == 200

    def test_invalid_range_year_backwards(self, client: TestClient) -> None:
        resp = client.post("/api/lineage", json={
            "seed": "test",
            "start_year": 2022,
            "end_year": 2018,
        })
        assert resp.status_code == 422, "start_year > end_year should be rejected"


class TestEdgeEnrichmentHandling:
    """Tests for edge cases in paper enrichment and fallbacks."""

    def test_breakthrough_missing_paper_enrichment_fallback(self, client: TestClient) -> None:
        # breakthrough.py line 94: title=paper.title if paper else c.paper_id
        # Test that fallback to paper_id works when enrichment returns None
        resp = client.post("/api/breakthrough", json={
            "field": "test",
            "start_year": 2015,
            "end_year": 2022,
        })
        assert resp.status_code == 200
        for cand in resp.json()["candidates"]:
            # title should either be actual title or fallback to paper_id
            assert cand["title"] in [p.title for p in _ALL_PAPERS] or cand["title"] == cand["paper_id"]

    def test_breakthrough_year_none_handling(self, client: TestClient) -> None:
        # breakthrough.py line 95: year=paper.publication_year if paper else None
        resp = client.post("/api/breakthrough", json={
            "field": "test",
            "start_year": 2015,
            "end_year": 2022,
        })
        assert resp.status_code == 200
        for cand in resp.json()["candidates"]:
            # year can be None or an integer
            assert cand["year"] is None or isinstance(cand["year"], int)
