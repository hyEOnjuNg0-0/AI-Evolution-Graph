"""Unit tests for OpenAIEmbeddingClient."""

from unittest.mock import MagicMock, patch

import pytest

from aievograph.infrastructure.openai_embedding_client import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    OpenAIEmbeddingClient,
)


def _make_embedding_item(index: int, dim: int = EMBEDDING_DIMENSIONS) -> MagicMock:
    item = MagicMock()
    item.embedding = [float(index)] * dim
    return item


def _make_response(*items: MagicMock) -> MagicMock:
    response = MagicMock()
    response.data = list(items)
    return response


@pytest.fixture()
def mock_openai_class():
    with patch("aievograph.infrastructure.openai_embedding_client.OpenAI") as cls:
        yield cls


@pytest.fixture()
def client(mock_openai_class):
    return OpenAIEmbeddingClient(api_key="test-key")


class TestEmbed:
    def test_returns_vector_of_correct_dimension(self, client, mock_openai_class):
        item = _make_embedding_item(0)
        mock_openai_class.return_value.embeddings.create.return_value = _make_response(item)

        result = client.embed("attention is all you need")

        assert len(result) == EMBEDDING_DIMENSIONS

    def test_calls_correct_model(self, client, mock_openai_class):
        mock_openai_class.return_value.embeddings.create.return_value = _make_response(
            _make_embedding_item(0)
        )

        client.embed("some query")

        mock_openai_class.return_value.embeddings.create.assert_called_once_with(
            input="some query",
            model=EMBEDDING_MODEL,
        )

    def test_returns_first_data_item_embedding(self, client, mock_openai_class):
        item0 = _make_embedding_item(1)
        item1 = _make_embedding_item(2)
        mock_openai_class.return_value.embeddings.create.return_value = _make_response(item0, item1)

        result = client.embed("text")

        assert result == item0.embedding


class TestEmbedBatch:
    def test_returns_one_vector_per_input(self, client, mock_openai_class):
        items = [_make_embedding_item(i) for i in range(3)]
        mock_openai_class.return_value.embeddings.create.return_value = _make_response(*items)

        results = client.embed_batch(["a", "b", "c"])

        assert len(results) == 3

    def test_preserves_order(self, client, mock_openai_class):
        items = [_make_embedding_item(i) for i in range(3)]
        mock_openai_class.return_value.embeddings.create.return_value = _make_response(*items)

        results = client.embed_batch(["a", "b", "c"])

        for i, result in enumerate(results):
            assert result == items[i].embedding

    def test_empty_input_returns_empty_list_without_api_call(self, client, mock_openai_class):
        result = client.embed_batch([])

        assert result == []
        mock_openai_class.return_value.embeddings.create.assert_not_called()

    def test_each_vector_has_correct_dimension(self, client, mock_openai_class):
        items = [_make_embedding_item(i) for i in range(2)]
        mock_openai_class.return_value.embeddings.create.return_value = _make_response(*items)

        results = client.embed_batch(["x", "y"])

        assert all(len(v) == EMBEDDING_DIMENSIONS for v in results)
