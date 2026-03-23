"""Unit tests for LLMEntityNormalizer and _find_candidate_clusters."""

from unittest.mock import MagicMock

import pytest

from aievograph.domain.models import Method, NormalizationMap
from aievograph.infrastructure.llm_entity_normalizer import (
    LLMEntityNormalizer,
    _find_candidate_clusters,
    _trigrams,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _method(name: str) -> Method:
    return Method(name=name, method_type="Model")


def _make_client(groups: list[dict]) -> MagicMock:
    """Return a mock OpenAI client that returns the given normalization groups."""
    from aievograph.infrastructure.llm_entity_normalizer import (
        _NormalizationGroup,
        _NormalizationResponse,
    )

    response_obj = _NormalizationResponse(
        groups=[_NormalizationGroup(**g) for g in groups]
    )
    client = MagicMock()
    client.beta.chat.completions.parse.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(parsed=response_obj))]
    )
    return client


# ---------------------------------------------------------------------------
# Tests: _trigrams
# ---------------------------------------------------------------------------

class TestTrigrams:
    def test_empty_string_returns_single_token(self) -> None:
        # _key("!!!") == "" — empty keys still produce a token so they can be
        # matched against each other in the inverted index.
        assert _trigrams("") == {""}

    def test_single_char_returns_single_token(self) -> None:
        assert _trigrams("a") == {"a"}

    def test_two_chars_returns_single_token(self) -> None:
        assert _trigrams("ab") == {"ab"}

    def test_three_chars_returns_one_trigram(self) -> None:
        assert _trigrams("abc") == {"abc"}

    def test_four_chars_returns_two_trigrams(self) -> None:
        assert _trigrams("bert") == {"ber", "ert"}

    def test_overlapping_trigrams(self) -> None:
        assert _trigrams("roberta") == {"rob", "obe", "ber", "ert", "rta"}

    def test_shared_trigrams_between_similar_names(self) -> None:
        # "bert" and "roberta" share "ber" and "ert" — must appear as candidates
        assert _trigrams("bert") & _trigrams("roberta") == {"ber", "ert"}

    def test_no_shared_trigrams_between_dissimilar_names(self) -> None:
        # "gpt3" and "bert" share no trigrams — should not be a candidate pair
        assert _trigrams("gpt3") & _trigrams("bert") == set()


# ---------------------------------------------------------------------------
# Tests: _find_candidate_clusters
# ---------------------------------------------------------------------------

class TestFindCandidateClusters:
    def test_empty_input(self) -> None:
        assert _find_candidate_clusters([]) == []

    def test_no_similar_names(self) -> None:
        names = ["BERT", "ResNet", "LSTM", "Transformer"]
        assert _find_candidate_clusters(names) == []

    def test_groups_case_variants(self) -> None:
        names = ["BERT", "bert", "Bert"]
        clusters = _find_candidate_clusters(names)
        assert len(clusters) == 1
        assert set(clusters[0]) == {"BERT", "bert", "Bert"}

    def test_groups_punctuation_variants(self) -> None:
        names = ["GPT-3", "GPT3", "gpt3"]
        clusters = _find_candidate_clusters(names)
        assert len(clusters) == 1
        assert set(clusters[0]) == {"GPT-3", "GPT3", "gpt3"}

    def test_distinct_names_not_grouped(self) -> None:
        # "BERT" and "GPT" are not similar enough
        names = ["BERT", "GPT", "bert"]
        clusters = _find_candidate_clusters(names)
        # Only "BERT" and "bert" should cluster; "GPT" stays alone
        assert len(clusters) == 1
        assert set(clusters[0]) == {"BERT", "bert"}

    def test_single_name_not_clustered(self) -> None:
        assert _find_candidate_clusters(["BERT"]) == []


# ---------------------------------------------------------------------------
# Tests: LLMEntityNormalizer
# ---------------------------------------------------------------------------

class TestLLMEntityNormalizer:
    def test_returns_empty_map_when_no_similar_names(self) -> None:
        client = MagicMock()
        normalizer = LLMEntityNormalizer(client)
        methods = [_method("BERT"), _method("ResNet"), _method("LSTM")]

        result = normalizer.normalize(methods)

        assert result.mapping == {}
        client.beta.chat.completions.parse.assert_not_called()

    def test_calls_llm_when_similar_names_exist(self) -> None:
        client = _make_client([{"canonical": "BERT", "variants": ["bert"]}])
        normalizer = LLMEntityNormalizer(client)

        normalizer.normalize([_method("BERT"), _method("bert")])

        client.beta.chat.completions.parse.assert_called_once()

    def test_builds_mapping_from_llm_response(self) -> None:
        client = _make_client([
            {"canonical": "BERT", "variants": ["bert", "Bert"]},
        ])
        normalizer = LLMEntityNormalizer(client)

        result = normalizer.normalize([_method("BERT"), _method("bert"), _method("Bert")])

        assert result.mapping == {"bert": "BERT", "Bert": "BERT"}

    def test_canonical_itself_not_in_mapping(self) -> None:
        client = _make_client([{"canonical": "BERT", "variants": ["BERT", "bert"]}])
        normalizer = LLMEntityNormalizer(client)

        result = normalizer.normalize([_method("BERT"), _method("bert")])

        assert "BERT" not in result.mapping

    def test_handles_none_parsed_gracefully(self) -> None:
        client = MagicMock()
        client.beta.chat.completions.parse.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(parsed=None))]
        )
        normalizer = LLMEntityNormalizer(client)

        # Force a cluster to exist so LLM is called
        result = normalizer.normalize([_method("BERT"), _method("bert")])

        assert result.mapping == {}

    def test_uses_specified_model(self) -> None:
        client = _make_client([{"canonical": "BERT", "variants": ["bert"]}])
        normalizer = LLMEntityNormalizer(client, model="gpt-4o-mini")

        normalizer.normalize([_method("BERT"), _method("bert")])

        call_kwargs = client.beta.chat.completions.parse.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"

    def test_empty_methods_list(self) -> None:
        client = MagicMock()
        normalizer = LLMEntityNormalizer(client)

        result = normalizer.normalize([])

        assert result.mapping == {}
        client.beta.chat.completions.parse.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _llm_normalize batching
# ---------------------------------------------------------------------------

def _make_parsed_response(groups: list[dict]) -> MagicMock:
    """Return a mock completions.parse() response with the given groups."""
    from aievograph.infrastructure.llm_entity_normalizer import (
        _NormalizationGroup,
        _NormalizationResponse,
    )
    obj = _NormalizationResponse(groups=[_NormalizationGroup(**g) for g in groups])
    return MagicMock(choices=[MagicMock(message=MagicMock(parsed=obj))])


def _make_null_response() -> MagicMock:
    return MagicMock(choices=[MagicMock(message=MagicMock(parsed=None))])


def _dummy_clusters(n: int) -> list[list[str]]:
    return [[f"method_{i}_a", f"method_{i}_b"] for i in range(n)]


class TestLLMNormalizeBatching:
    def test_50_clusters_makes_one_llm_call(self) -> None:
        client = _make_client([])
        normalizer = LLMEntityNormalizer(client)

        normalizer._llm_normalize(_dummy_clusters(50))

        assert client.beta.chat.completions.parse.call_count == 1

    def test_51_clusters_makes_two_llm_calls(self) -> None:
        client = _make_client([])
        normalizer = LLMEntityNormalizer(client)

        normalizer._llm_normalize(_dummy_clusters(51))

        assert client.beta.chat.completions.parse.call_count == 2

    def test_multi_batch_results_are_merged(self) -> None:
        client = MagicMock()
        client.beta.chat.completions.parse.side_effect = [
            _make_parsed_response([{"canonical": "BERT", "variants": ["bert"]}]),
            _make_parsed_response([{"canonical": "GPT-3", "variants": ["gpt3"]}]),
        ]
        normalizer = LLMEntityNormalizer(client)

        result = normalizer._llm_normalize(_dummy_clusters(51))

        assert result.mapping == {"bert": "BERT", "gpt3": "GPT-3"}

    def test_null_batch_does_not_discard_other_batches(self) -> None:
        client = MagicMock()
        client.beta.chat.completions.parse.side_effect = [
            _make_parsed_response([{"canonical": "BERT", "variants": ["bert"]}]),
            _make_null_response(),
        ]
        normalizer = LLMEntityNormalizer(client)

        result = normalizer._llm_normalize(_dummy_clusters(51))

        assert result.mapping == {"bert": "BERT"}
