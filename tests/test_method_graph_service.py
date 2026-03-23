"""Unit tests for MethodGraphService."""

from unittest.mock import MagicMock, call

import pytest

from aievograph.domain.models import (
    ExtractionResult,
    Method,
    MethodRelation,
    NormalizationMap,
    Paper,
)
from aievograph.domain.services.method_graph_service import MethodGraphService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _method(name: str) -> Method:
    return Method(name=name, method_type="Model")


def _rel(src: str, tgt: str, rtype: str = "IMPROVES") -> MethodRelation:
    return MethodRelation(
        source_method=src,
        target_method=tgt,
        relation_type=rtype,  # type: ignore[arg-type]
        evidence=f"{src} {rtype} {tgt}",
    )


def _paper(paper_id: str, abstract: str | None = "Some abstract.") -> Paper:
    return Paper(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        publication_year=2022,
        abstract=abstract,
    )


def _make_service(
    extraction_results: list[tuple[str, ExtractionResult]],
    norm_mapping: dict[str, str] | None = None,
) -> tuple[MethodGraphService, MagicMock]:
    """Return (service, repo_mock) with stubbed extraction and normalization."""
    repo = MagicMock()

    extraction_service = MagicMock()
    extraction_service.extract_from_papers.return_value = extraction_results

    norm_map = NormalizationMap(mapping=norm_mapping or {})
    normalization_service = MagicMock()
    normalization_service.normalize.return_value = (extraction_results, norm_map)

    service = MethodGraphService(repo, extraction_service, normalization_service)
    return service, repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMethodGraphService:
    def test_empty_papers_returns_empty_map(self) -> None:
        service, _ = _make_service([])

        result = service.build_method_graph([])

        assert result.mapping == {}

    def test_returns_normalization_map(self) -> None:
        extraction_results = [("P1", ExtractionResult(methods=[_method("BERT")]))]
        service, _ = _make_service(extraction_results, norm_mapping={"bert": "BERT"})

        norm_map = service.build_method_graph([_paper("P1")])

        assert norm_map.mapping == {"bert": "BERT"}

    def test_upserts_all_methods(self) -> None:
        extraction_results = [
            ("P1", ExtractionResult(methods=[_method("BERT"), _method("GPT-3")])),
        ]
        service, repo = _make_service(extraction_results)

        service.build_method_graph([_paper("P1")])

        upserted_names = {c.args[0].name for c in repo.upsert_method.call_args_list}
        assert upserted_names == {"BERT", "GPT-3"}

    def test_creates_uses_edges_for_all_methods(self) -> None:
        extraction_results = [
            ("P1", ExtractionResult(methods=[_method("BERT")])),
            ("P2", ExtractionResult(methods=[_method("GPT-3")])),
        ]
        service, repo = _make_service(extraction_results)

        service.build_method_graph([_paper("P1"), _paper("P2")])

        uses_calls = {(c.args[0], c.args[1]) for c in repo.create_paper_uses_method.call_args_list}
        assert uses_calls == {("P1", "BERT"), ("P2", "GPT-3")}

    def test_creates_all_method_relations(self) -> None:
        relation = _rel("BERT", "RoBERTa")
        extraction_results = [
            ("P1", ExtractionResult(relations=[relation])),
        ]
        service, repo = _make_service(extraction_results)

        service.build_method_graph([_paper("P1")])

        repo.create_method_relation.assert_called_once_with(relation)

    def test_multiple_papers_multiple_relations(self) -> None:
        r1 = _rel("BERT", "RoBERTa")
        r2 = _rel("GPT-2", "GPT-3", "EXTENDS")
        extraction_results = [
            ("P1", ExtractionResult(relations=[r1])),
            ("P2", ExtractionResult(relations=[r2])),
        ]
        service, repo = _make_service(extraction_results)

        service.build_method_graph([_paper("P1"), _paper("P2")])

        assert repo.create_method_relation.call_count == 2
        called_relations = {c.args[0] for c in repo.create_method_relation.call_args_list}
        assert called_relations == {r1, r2}

    def test_no_relations_no_relation_calls(self) -> None:
        extraction_results = [("P1", ExtractionResult(methods=[_method("BERT")]))]
        service, repo = _make_service(extraction_results)

        service.build_method_graph([_paper("P1")])

        repo.create_method_relation.assert_not_called()

    def test_delegates_to_extraction_service(self) -> None:
        service, _ = _make_service([])
        papers = [_paper("P1"), _paper("P2")]

        service.build_method_graph(papers)

        service._extraction.extract_from_papers.assert_called_once_with(papers)

    def test_passes_extraction_results_to_normalization(self) -> None:
        extraction_results = [("P1", ExtractionResult(methods=[_method("BERT")]))]
        service, _ = _make_service(extraction_results)
        papers = [_paper("P1")]

        service.build_method_graph(papers)

        service._normalization.normalize.assert_called_once_with(extraction_results, None)
