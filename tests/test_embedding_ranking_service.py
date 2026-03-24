"""Unit tests for EmbeddingRankingService (Layer C Step 4.2)."""

import math

import pytest

from aievograph.domain.models import Paper, ScoredPaper, Subgraph
from aievograph.domain.ports.embedding_port import EmbeddingPort
from aievograph.domain.ports.paper_embedding_repository import PaperEmbeddingRepositoryPort
from aievograph.domain.services.embedding_ranking_service import (
    EmbeddingRankingService,
    _cosine_similarity,
    _normalize,
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class StubEmbeddingPort(EmbeddingPort):
    """Returns a fixed embedding vector for every query."""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    def embed(self, text: str) -> list[float]:
        return self._vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._vector for _ in texts]


class StubPaperEmbeddingRepo(PaperEmbeddingRepositoryPort):
    """Returns pre-set embeddings; papers not in the dict are omitted."""

    def __init__(self, stored: dict[str, list[float]]) -> None:
        self._stored = stored

    def get_embeddings(self, paper_ids: list[str]) -> dict[str, list[float]]:
        return {pid: self._stored[pid] for pid in paper_ids if pid in self._stored}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paper(paper_id: str) -> Paper:
    return Paper(paper_id=paper_id, title=f"Paper {paper_id}", publication_year=2020)


def _make_subgraph(*paper_ids: str) -> Subgraph:
    return Subgraph(
        papers=[ScoredPaper(paper=_make_paper(pid), score=0.5) for pid in paper_ids]
    )


def _service(
    query_vec: list[float],
    stored: dict[str, list[float]],
) -> EmbeddingRankingService:
    return EmbeddingRankingService(
        embedding_port=StubEmbeddingPort(query_vec),
        paper_embedding_repo=StubPaperEmbeddingRepo(stored),
    )


# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors_return_one(self):
        assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_return_zero(self):
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_return_minus_one(self):
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_a_returns_zero(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 2.0]) == pytest.approx(0.0)

    def test_dimension_mismatch_raises_value_error(self):
        with pytest.raises(ValueError, match="dimension mismatch"):
            _cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_known_value(self):
        # [1,1] vs [1,0]: cos = 1/sqrt(2)
        expected = 1.0 / math.sqrt(2)
        assert _cosine_similarity([1.0, 1.0], [1.0, 0.0]) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# _normalize (shared function — smoke test only; full tests in centrality suite)
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_max_becomes_one(self):
        result = _normalize({"a": 4.0, "b": 2.0})
        assert result["a"] == pytest.approx(1.0)
        assert result["b"] == pytest.approx(0.5)

    def test_negatives_clipped_to_zero(self):
        result = _normalize({"a": 2.0, "b": -1.0})
        assert result["b"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# EmbeddingRankingService.rank()
# ---------------------------------------------------------------------------

class TestRank:
    def test_empty_query_raises(self):
        svc = _service([1.0, 0.0], {})
        with pytest.raises(ValueError, match="query"):
            svc.rank("   ", _make_subgraph("p1"))

    def test_empty_subgraph_returns_empty_list(self):
        svc = _service([1.0, 0.0], {})
        assert svc.rank("query", Subgraph()) == []

    def test_paper_with_identical_embedding_scores_one(self):
        vec = [1.0, 0.0]
        svc = _service(vec, {"p1": vec})
        result = svc.rank("query", _make_subgraph("p1"))
        assert result[0].score == pytest.approx(1.0)

    def test_missing_embedding_defaults_to_zero(self):
        svc = _service([1.0, 0.0], {"p1": [1.0, 0.0]})
        result = svc.rank("query", _make_subgraph("p1", "p2"))
        p2 = next(sp for sp in result if sp.paper.paper_id == "p2")
        assert p2.score == pytest.approx(0.0)

    def test_higher_similarity_ranks_first(self):
        query = [1.0, 0.0]
        # p1 is identical to query; p2 is orthogonal → p1 ranks first.
        svc = _service(query, {"p1": [1.0, 0.0], "p2": [0.0, 1.0]})
        result = svc.rank("query", _make_subgraph("p1", "p2"))
        assert result[0].paper.paper_id == "p1"

    def test_scores_are_non_negative(self):
        query = [1.0, 0.0]
        # p1 is opposite direction → raw cosine = -1 → clipped to 0.
        svc = _service(query, {"p1": [-1.0, 0.0]})
        result = svc.rank("query", _make_subgraph("p1"))
        assert result[0].score >= 0.0

    def test_tiebreaker_is_paper_id_ascending(self):
        vec = [1.0, 0.0]
        svc = _service(vec, {"p_b": vec, "p_a": vec})
        result = svc.rank("query", _make_subgraph("p_b", "p_a"))
        assert result[0].paper.paper_id == "p_a"

    def test_all_missing_embeddings_return_zeros(self):
        svc = _service([1.0, 0.0], {})
        result = svc.rank("query", _make_subgraph("p1", "p2"))
        assert all(sp.score == pytest.approx(0.0) for sp in result)
