"""Unit tests for LLMMethodExtractor (OpenAI client mocked)."""

from unittest.mock import MagicMock, patch

import pytest

from aievograph.domain.models import ExtractionResult, Method, MethodRelation
from aievograph.infrastructure.llm_method_extractor import LLMMethodExtractor, _merge, _sanitize


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(first_result: ExtractionResult, gleaned_result: ExtractionResult) -> MagicMock:
    """Return a mock OpenAI client whose parse() alternates between two results."""
    client = MagicMock()
    _make_parse_response = lambda result: MagicMock(
        choices=[MagicMock(message=MagicMock(parsed=result))]
    )
    client.beta.chat.completions.parse.side_effect = [
        _make_parse_response(first_result),
        _make_parse_response(gleaned_result),
    ]
    return client


def _method(name: str) -> Method:
    return Method(name=name, method_type="Model", description=f"{name} description")


def _relation(src: str, tgt: str, rtype: str = "IMPROVES") -> MethodRelation:
    return MethodRelation(
        source_method=src,
        target_method=tgt,
        relation_type=rtype,  # type: ignore[arg-type]
        evidence=f"{src} {rtype.lower()} {tgt}",
    )


# ---------------------------------------------------------------------------
# Tests: LLMMethodExtractor
# ---------------------------------------------------------------------------

class TestExtract:
    def test_calls_llm_twice_for_gleaning(self) -> None:
        client = _make_client(ExtractionResult(), ExtractionResult())
        extractor = LLMMethodExtractor(client)

        extractor.extract("Some abstract.")

        assert client.beta.chat.completions.parse.call_count == 2

    def test_result_contains_methods_from_both_passes(self) -> None:
        first = ExtractionResult(methods=[_method("BERT")])
        gleaned = ExtractionResult(methods=[_method("GPT-3")])
        client = _make_client(first, gleaned)
        extractor = LLMMethodExtractor(client)

        result = extractor.extract("abstract")

        names = {m.name for m in result.methods}
        assert names == {"BERT", "GPT-3"}

    def test_deduplicates_methods_by_name(self) -> None:
        bert = _method("BERT")
        first = ExtractionResult(methods=[bert])
        gleaned = ExtractionResult(methods=[bert])  # duplicate
        client = _make_client(first, gleaned)
        extractor = LLMMethodExtractor(client)

        result = extractor.extract("abstract")

        assert len(result.methods) == 1
        assert result.methods[0].name == "BERT"

    def test_first_pass_wins_on_name_collision(self) -> None:
        first_bert = Method(name="BERT", method_type="Model", description="first pass")
        gleaned_bert = Method(name="BERT", method_type="Model", description="gleaned pass")
        first = ExtractionResult(methods=[first_bert])
        gleaned = ExtractionResult(methods=[gleaned_bert])
        client = _make_client(first, gleaned)
        extractor = LLMMethodExtractor(client)

        result = extractor.extract("abstract")

        assert result.methods[0].description == "first pass"

    def test_deduplicates_relations_by_key(self) -> None:
        rel = _relation("BERT", "ELMo")
        first = ExtractionResult(relations=[rel])
        gleaned = ExtractionResult(relations=[rel])  # duplicate
        client = _make_client(first, gleaned)
        extractor = LLMMethodExtractor(client)

        result = extractor.extract("abstract")

        assert len(result.relations) == 1

    def test_merges_distinct_relations(self) -> None:
        first = ExtractionResult(relations=[_relation("GPT-3", "GPT-2", "EXTENDS")])
        gleaned = ExtractionResult(relations=[_relation("GPT-3", "BERT", "IMPROVES")])
        client = _make_client(first, gleaned)
        extractor = LLMMethodExtractor(client)

        result = extractor.extract("abstract")

        assert len(result.relations) == 2

    def test_handles_none_parsed_gracefully(self) -> None:
        client = MagicMock()
        client.beta.chat.completions.parse.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(parsed=None))]
        )
        extractor = LLMMethodExtractor(client)

        result = extractor.extract("abstract")

        assert result.methods == []
        assert result.relations == []

    def test_uses_specified_model(self) -> None:
        client = _make_client(ExtractionResult(), ExtractionResult())
        extractor = LLMMethodExtractor(client, model="gpt-4o-mini")

        extractor.extract("abstract")

        calls = client.beta.chat.completions.parse.call_args_list
        assert all(c.kwargs["model"] == "gpt-4o-mini" for c in calls)


# ---------------------------------------------------------------------------
# Tests: _sanitize helper
# ---------------------------------------------------------------------------

class TestSanitize:
    def test_line_separator_replaced_with_space(self) -> None:
        assert _sanitize("foo\u2028bar") == "foo bar"

    def test_paragraph_separator_replaced_with_space(self) -> None:
        assert _sanitize("foo\u2029bar") == "foo bar"

    def test_null_byte_removed(self) -> None:
        assert _sanitize("foo\x00bar") == "foobar"

    def test_clean_text_unchanged(self) -> None:
        text = "We propose BERT, a bidirectional Transformer model."
        assert _sanitize(text) == text

    def test_multiple_problematic_chars(self) -> None:
        assert _sanitize("\x00\u2028\u2029") == "  "

    def test_extract_sanitizes_before_llm(self) -> None:
        # Abstract with U+2028 must be cleaned before reaching the LLM call.
        client = _make_client(ExtractionResult(), ExtractionResult())
        extractor = LLMMethodExtractor(client)

        extractor.extract("intro\u2028body\u2029end\x00.")

        call_content = client.beta.chat.completions.parse.call_args_list[0].kwargs["messages"][1]["content"]
        assert "\u2028" not in call_content
        assert "\u2029" not in call_content
        assert "\x00" not in call_content


# ---------------------------------------------------------------------------
# Tests: _merge helper
# ---------------------------------------------------------------------------

class TestMerge:
    def test_empty_inputs(self) -> None:
        result = _merge(ExtractionResult(), ExtractionResult())
        assert result.methods == []
        assert result.relations == []

    def test_combines_all_methods(self) -> None:
        first = ExtractionResult(methods=[_method("A"), _method("B")])
        gleaned = ExtractionResult(methods=[_method("C")])
        result = _merge(first, gleaned)
        assert {m.name for m in result.methods} == {"A", "B", "C"}

    def test_combines_all_relations(self) -> None:
        first = ExtractionResult(relations=[_relation("A", "B")])
        gleaned = ExtractionResult(relations=[_relation("C", "D")])
        result = _merge(first, gleaned)
        assert len(result.relations) == 2
