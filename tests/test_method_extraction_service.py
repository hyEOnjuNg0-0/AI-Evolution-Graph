"""Unit tests for MethodExtractionService."""

from unittest.mock import MagicMock

import pytest

from aievograph.domain.models import (
    ExtractionResult,
    Method,
    MethodRelation,
    Paper,
)
from aievograph.domain.services.method_extraction_service import MethodExtractionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_paper(paper_id: str, abstract: str | None = "Some abstract text.") -> Paper:
    return Paper(paper_id=paper_id, title=f"Paper {paper_id}", publication_year=2023, abstract=abstract)


def _make_extractor(result: ExtractionResult | None = None) -> MagicMock:
    extractor = MagicMock()
    extractor.extract = MagicMock(return_value=result or ExtractionResult())
    return extractor


def _make_result(method_names: list[str]) -> ExtractionResult:
    methods = [Method(name=n, method_type="Method") for n in method_names]
    return ExtractionResult(methods=methods)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractFromPapers:
    def test_returns_empty_for_empty_list(self) -> None:
        service = MethodExtractionService(_make_extractor())
        assert service.extract_from_papers([]) == []

    def test_skips_paper_without_abstract(self) -> None:
        extractor = _make_extractor()
        service = MethodExtractionService(extractor)

        service.extract_from_papers([_make_paper("P1", abstract=None)])

        extractor.extract.assert_not_called()

    def test_skips_paper_with_empty_abstract(self) -> None:
        extractor = _make_extractor()
        service = MethodExtractionService(extractor)

        service.extract_from_papers([_make_paper("P1", abstract="")])

        extractor.extract.assert_not_called()

    def test_calls_extractor_for_each_paper_with_abstract(self) -> None:
        extractor = _make_extractor()
        service = MethodExtractionService(extractor)
        papers = [_make_paper("P1"), _make_paper("P2"), _make_paper("P3", abstract=None)]

        service.extract_from_papers(papers)

        assert extractor.extract.call_count == 2

    def test_passes_abstract_to_extractor(self) -> None:
        extractor = _make_extractor()
        service = MethodExtractionService(extractor)
        paper = _make_paper("P1", abstract="We propose a new attention mechanism.")

        service.extract_from_papers([paper])

        extractor.extract.assert_called_once_with("We propose a new attention mechanism.")

    def test_returns_paper_id_with_result(self) -> None:
        result = _make_result(["BERT"])
        extractor = _make_extractor(result)
        service = MethodExtractionService(extractor)

        output = service.extract_from_papers([_make_paper("P42")])

        assert len(output) == 1
        paper_id, extraction = output[0]
        assert paper_id == "P42"
        assert extraction is result

    def test_returns_one_entry_per_paper_with_abstract(self) -> None:
        extractor = _make_extractor()
        service = MethodExtractionService(extractor)
        papers = [_make_paper(f"P{i}") for i in range(5)]

        output = service.extract_from_papers(papers)

        assert len(output) == 5

    def test_mixed_papers_returns_only_those_with_abstract(self) -> None:
        extractor = _make_extractor()
        service = MethodExtractionService(extractor)
        papers = [
            _make_paper("has1", abstract="abstract one"),
            _make_paper("none1", abstract=None),
            _make_paper("has2", abstract="abstract two"),
            _make_paper("none2", abstract=None),
        ]

        output = service.extract_from_papers(papers)

        ids = [pid for pid, _ in output]
        assert ids == ["has1", "has2"]
