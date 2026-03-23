"""Unit tests for VectorRetrievalService."""

from unittest.mock import MagicMock

import pytest

from aievograph.domain.models import Paper, ScoredPaper
from aievograph.domain.services.vector_retrieval_service import (
    _MAX_TEXT_CHARS,
    VectorRetrievalService,
)


def _make_paper(paper_id: str, abstract: str | None = None) -> Paper:
    return Paper(
        paper_id=paper_id,
        title=f"Title of {paper_id}",
        publication_year=2020,
        abstract=abstract,
    )


def _make_scored_paper(paper_id: str, score: float) -> ScoredPaper:
    return ScoredPaper(paper=_make_paper(paper_id), score=score)


@pytest.fixture()
def embedding_port():
    return MagicMock()


@pytest.fixture()
def vector_repo():
    return MagicMock()


@pytest.fixture()
def service(embedding_port, vector_repo):
    return VectorRetrievalService(embedding_port=embedding_port, vector_repo=vector_repo)


def test_create_vector_index_called_on_init(embedding_port, vector_repo):
    VectorRetrievalService(embedding_port=embedding_port, vector_repo=vector_repo)
    vector_repo.create_vector_index.assert_called_once()


class TestSearch:
    def test_embeds_query_and_calls_similarity_search(self, service, embedding_port, vector_repo):
        query_vec = [0.1] * 1536
        embedding_port.embed.return_value = query_vec
        vector_repo.similarity_search.return_value = [_make_scored_paper("p1", 0.9)]

        results = service.search("transformer architecture", top_k=5)

        embedding_port.embed.assert_called_once_with("transformer architecture")
        vector_repo.similarity_search.assert_called_once_with(query_vec, 5)
        assert len(results) == 1

    def test_returns_empty_when_no_results(self, service, embedding_port, vector_repo):
        embedding_port.embed.return_value = [0.0] * 1536
        vector_repo.similarity_search.return_value = []

        assert service.search("query") == []

    def test_default_top_k_is_ten(self, service, embedding_port, vector_repo):
        embedding_port.embed.return_value = [0.0] * 1536
        vector_repo.similarity_search.return_value = []

        service.search("query")

        _, call_top_k = vector_repo.similarity_search.call_args.args
        assert call_top_k == 10

    def test_raises_on_empty_query(self, service):
        with pytest.raises(ValueError, match="query must not be empty"):
            service.search("")

    def test_raises_on_whitespace_only_query(self, service):
        with pytest.raises(ValueError, match="query must not be empty"):
            service.search("   ")

    def test_raises_on_non_positive_top_k(self, service):
        with pytest.raises(ValueError, match="top_k"):
            service.search("valid query", top_k=0)

    def test_raises_on_negative_top_k(self, service):
        with pytest.raises(ValueError, match="top_k"):
            service.search("valid query", top_k=-1)


class TestEmbedAndStorePapers:
    def test_stores_embedding_for_each_paper(self, service, embedding_port, vector_repo):
        papers = [_make_paper(f"p{i}") for i in range(3)]
        vector_repo.get_paper_ids_without_embedding.return_value = [f"p{i}" for i in range(3)]
        embedding_port.embed_batch.return_value = [[float(i)] * 5 for i in range(3)]

        service.embed_and_store_papers(papers, batch_size=10)

        assert vector_repo.store_embedding.call_count == 3

    def test_passes_correct_paper_ids(self, service, embedding_port, vector_repo):
        papers = [_make_paper("paper_a"), _make_paper("paper_b")]
        vector_repo.get_paper_ids_without_embedding.return_value = ["paper_a", "paper_b"]
        embedding_port.embed_batch.return_value = [[0.1] * 5, [0.2] * 5]

        service.embed_and_store_papers(papers)

        stored_ids = [call.args[0] for call in vector_repo.store_embedding.call_args_list]
        assert stored_ids == ["paper_a", "paper_b"]

    def test_batches_calls_to_embed_batch(self, service, embedding_port, vector_repo):
        papers = [_make_paper(f"p{i}") for i in range(5)]
        vector_repo.get_paper_ids_without_embedding.return_value = [f"p{i}" for i in range(5)]
        embedding_port.embed_batch.side_effect = [
            [[0.1] * 5, [0.2] * 5],
            [[0.3] * 5, [0.4] * 5],
            [[0.5] * 5],
        ]

        service.embed_and_store_papers(papers, batch_size=2)

        assert embedding_port.embed_batch.call_count == 3

    def test_embed_and_store_does_not_call_create_vector_index_for_empty_papers(self, service, embedding_port, vector_repo):
        vector_repo.reset_mock()  # clear the __init__ call
        service.embed_and_store_papers([])

        vector_repo.create_vector_index.assert_not_called()
        embedding_port.embed_batch.assert_not_called()
        vector_repo.store_embedding.assert_not_called()

    def test_raises_on_zero_batch_size(self, service):
        with pytest.raises(ValueError, match="batch_size"):
            service.embed_and_store_papers([_make_paper("p1")], batch_size=0)

    def test_raises_on_negative_batch_size(self, service):
        with pytest.raises(ValueError, match="batch_size"):
            service.embed_and_store_papers([_make_paper("p1")], batch_size=-5)

    def test_raises_on_embedding_count_mismatch(self, service, embedding_port, vector_repo):
        papers = [_make_paper("p1"), _make_paper("p2")]
        vector_repo.get_paper_ids_without_embedding.return_value = ["p1", "p2"]
        # API returns only 1 embedding for 2 papers
        embedding_port.embed_batch.return_value = [[0.1] * 5]

        with pytest.raises(RuntimeError, match="Embedding count mismatch"):
            service.embed_and_store_papers(papers, batch_size=10)

    def test_deduplicates_papers_by_paper_id(self, service, embedding_port, vector_repo):
        papers = [_make_paper("p1"), _make_paper("p1"), _make_paper("p2")]
        vector_repo.get_paper_ids_without_embedding.return_value = ["p1", "p2"]
        embedding_port.embed_batch.return_value = [[0.1] * 5, [0.2] * 5]

        service.embed_and_store_papers(papers)

        # Only 2 unique papers should be stored
        assert vector_repo.store_embedding.call_count == 2

    def test_deduplication_preserves_order(self, service, embedding_port, vector_repo):
        papers = [_make_paper("p2"), _make_paper("p1"), _make_paper("p2")]
        vector_repo.get_paper_ids_without_embedding.return_value = ["p2", "p1"]
        embedding_port.embed_batch.return_value = [[0.2] * 5, [0.1] * 5]

        service.embed_and_store_papers(papers)

        stored_ids = [call.args[0] for call in vector_repo.store_embedding.call_args_list]
        assert stored_ids == ["p2", "p1"]

    def test_skips_papers_with_existing_embeddings(self, service, embedding_port, vector_repo):
        papers = [_make_paper("p1"), _make_paper("p2"), _make_paper("p3")]
        vector_repo.get_paper_ids_without_embedding.return_value = ["p2"]
        embedding_port.embed_batch.return_value = [[0.2] * 5]

        service.embed_and_store_papers(papers)

        stored_ids = [call.args[0] for call in vector_repo.store_embedding.call_args_list]
        assert stored_ids == ["p2"]

    def test_does_nothing_when_all_papers_already_embedded(self, service, embedding_port, vector_repo):
        papers = [_make_paper("p1"), _make_paper("p2")]
        vector_repo.get_paper_ids_without_embedding.return_value = []

        service.embed_and_store_papers(papers)

        embedding_port.embed_batch.assert_not_called()
        vector_repo.store_embedding.assert_not_called()


class TestPaperToText:
    def test_title_only_when_no_abstract(self):
        paper = _make_paper("p1", abstract=None)
        text = VectorRetrievalService._paper_to_text(paper)
        assert text == paper.title

    def test_title_and_abstract_joined(self):
        paper = _make_paper("p1", abstract="This paper proposes a new model.")
        text = VectorRetrievalService._paper_to_text(paper)
        assert text == f"{paper.title} {paper.abstract}"

    def test_truncates_to_max_chars(self):
        long_abstract = "x" * (_MAX_TEXT_CHARS + 1000)
        paper = _make_paper("p1", abstract=long_abstract)
        text = VectorRetrievalService._paper_to_text(paper)
        assert len(text) == _MAX_TEXT_CHARS

    def test_short_text_not_truncated(self):
        paper = _make_paper("p1", abstract="short abstract")
        text = VectorRetrievalService._paper_to_text(paper)
        assert len(text) < _MAX_TEXT_CHARS
