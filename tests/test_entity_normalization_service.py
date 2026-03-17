"""Unit tests for EntityNormalizationService."""

from unittest.mock import MagicMock

import pytest

from aievograph.domain.models import (
    ExtractionResult,
    Method,
    MethodRelation,
    NormalizationMap,
)
from aievograph.domain.services.entity_normalization_service import (
    EntityNormalizationService,
    _apply_map,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _method(name: str, desc: str = "") -> Method:
    return Method(name=name, method_type="Model", description=desc or None)


def _rel(src: str, tgt: str, rtype: str = "IMPROVES") -> MethodRelation:
    return MethodRelation(
        source_method=src,
        target_method=tgt,
        relation_type=rtype,  # type: ignore[arg-type]
        evidence=f"{src} {rtype} {tgt}",
    )


def _make_normalizer(mapping: dict[str, str]) -> MagicMock:
    norm = MagicMock()
    norm.normalize = MagicMock(return_value=NormalizationMap(mapping=mapping))
    return norm


# ---------------------------------------------------------------------------
# Tests: _apply_map
# ---------------------------------------------------------------------------

class TestApplyMap:
    def test_renames_method_to_canonical(self) -> None:
        result = ExtractionResult(methods=[_method("bert")])
        norm_map = NormalizationMap(mapping={"bert": "BERT"})

        out = _apply_map(result, norm_map)

        assert len(out.methods) == 1
        assert out.methods[0].name == "BERT"

    def test_preserves_method_type_and_description(self) -> None:
        result = ExtractionResult(methods=[_method("bert", desc="A language model")])
        norm_map = NormalizationMap(mapping={"bert": "BERT"})

        out = _apply_map(result, norm_map)

        m = out.methods[0]
        assert m.method_type == "Model"
        assert m.description == "A language model"

    def test_deduplicates_methods_after_renaming(self) -> None:
        # "bert" and "Bert" both map to "BERT" → should collapse to one
        result = ExtractionResult(methods=[_method("bert"), _method("Bert")])
        norm_map = NormalizationMap(mapping={"bert": "BERT", "Bert": "BERT"})

        out = _apply_map(result, norm_map)

        assert len(out.methods) == 1
        assert out.methods[0].name == "BERT"

    def test_renames_relation_endpoints(self) -> None:
        result = ExtractionResult(relations=[_rel("bert", "elmo")])
        norm_map = NormalizationMap(mapping={"bert": "BERT", "elmo": "ELMo"})

        out = _apply_map(result, norm_map)

        assert out.relations[0].source_method == "BERT"
        assert out.relations[0].target_method == "ELMo"

    def test_deduplicates_relations_after_renaming(self) -> None:
        # Both relations map to (BERT, ELMo, IMPROVES) after normalization
        result = ExtractionResult(
            relations=[_rel("bert", "elmo"), _rel("BERT", "ELMo")]
        )
        norm_map = NormalizationMap(mapping={"bert": "BERT", "elmo": "ELMo"})

        out = _apply_map(result, norm_map)

        assert len(out.relations) == 1

    def test_unmapped_names_are_unchanged(self) -> None:
        result = ExtractionResult(methods=[_method("Transformer")])
        norm_map = NormalizationMap(mapping={})

        out = _apply_map(result, norm_map)

        assert out.methods[0].name == "Transformer"


# ---------------------------------------------------------------------------
# Tests: EntityNormalizationService
# ---------------------------------------------------------------------------

class TestEntityNormalizationService:
    def test_returns_empty_for_empty_input(self) -> None:
        service = EntityNormalizationService(_make_normalizer({}))
        results, norm_map = service.normalize([])
        assert results == []
        assert norm_map.mapping == {}

    def test_collects_all_unique_methods_for_normalizer(self) -> None:
        normalizer = _make_normalizer({})
        service = EntityNormalizationService(normalizer)
        r1 = ExtractionResult(methods=[_method("BERT"), _method("GPT-3")])
        r2 = ExtractionResult(methods=[_method("GPT-3"), _method("ResNet")])

        service.normalize([("P1", r1), ("P2", r2)])

        passed_methods: list[Method] = normalizer.normalize.call_args[0][0]
        names = {m.name for m in passed_methods}
        assert names == {"BERT", "GPT-3", "ResNet"}

    def test_applies_normalization_to_all_results(self) -> None:
        service = EntityNormalizationService(_make_normalizer({"bert": "BERT"}))
        result = ExtractionResult(methods=[_method("bert")])

        normalized, _ = service.normalize([("P1", result)])

        assert normalized[0][1].methods[0].name == "BERT"

    def test_returns_normalization_map(self) -> None:
        service = EntityNormalizationService(_make_normalizer({"bert": "BERT"}))

        _, norm_map = service.normalize([("P1", ExtractionResult())])

        assert norm_map.mapping == {"bert": "BERT"}

    def test_preserves_paper_ids_in_output(self) -> None:
        service = EntityNormalizationService(_make_normalizer({}))
        inputs = [("P1", ExtractionResult()), ("P42", ExtractionResult())]

        normalized, _ = service.normalize(inputs)

        assert [pid for pid, _ in normalized] == ["P1", "P42"]

    def test_first_occurrence_of_method_name_wins(self) -> None:
        """When the same method appears in multiple papers, first description is kept."""
        normalizer = _make_normalizer({})
        service = EntityNormalizationService(normalizer)
        r1 = ExtractionResult(methods=[_method("BERT", desc="first")])
        r2 = ExtractionResult(methods=[_method("BERT", desc="second")])

        service.normalize([("P1", r1), ("P2", r2)])

        passed: list[Method] = normalizer.normalize.call_args[0][0]
        bert = next(m for m in passed if m.name == "BERT")
        assert bert.description == "first"
