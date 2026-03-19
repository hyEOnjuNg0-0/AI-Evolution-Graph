import pytest

from aievograph.domain.models import Paper
from aievograph.domain.utils.paper_filter import (
    compute_citation_thresholds,
    filter_top_cited,
)


def _make_paper(paper_id: str, year: int, citations: int) -> Paper:
    return Paper(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        publication_year=year,
        citation_count=citations,
    )


class TestComputeCitationThresholds:
    def test_single_year_single_paper(self) -> None:
        papers = [_make_paper("P1", 2020, 100)]
        thresholds = compute_citation_thresholds(papers, top_percent=0.20)
        assert thresholds[2020] == 100

    def test_single_year_five_papers_top20(self) -> None:
        papers = [
            _make_paper("P1", 2020, 500),
            _make_paper("P2", 2020, 400),
            _make_paper("P3", 2020, 300),
            _make_paper("P4", 2020, 200),
            _make_paper("P5", 2020, 100),
        ]
        # top 20% of 5 = 1 paper -> threshold = 500
        thresholds = compute_citation_thresholds(papers, top_percent=0.20)
        assert thresholds[2020] == 500

    def test_multiple_years(self) -> None:
        papers = [
            _make_paper("P1", 2020, 500),
            _make_paper("P2", 2020, 100),
            _make_paper("P3", 2021, 300),
            _make_paper("P4", 2021, 50),
        ]
        thresholds = compute_citation_thresholds(papers, top_percent=0.50)
        assert thresholds[2020] == 500
        assert thresholds[2021] == 300

    def test_top50_of_ten_papers(self) -> None:
        papers = [_make_paper(f"P{i}", 2020, (10 - i) * 10) for i in range(10)]
        thresholds = compute_citation_thresholds(papers, top_percent=0.50)
        # top 50% of 10 = 5 papers, sorted desc: 100,90,80,70,60,...
        # cutoff_idx = ceil(10 * 0.5) - 1 = 4 -> sorted[4] = 60
        assert thresholds[2020] == 60


class TestFilterTopCited:
    def test_filters_below_threshold(self) -> None:
        papers = [
            _make_paper("P1", 2020, 500),
            _make_paper("P2", 2020, 400),
            _make_paper("P3", 2020, 300),
            _make_paper("P4", 2020, 200),
            _make_paper("P5", 2020, 100),
        ]
        result = filter_top_cited(papers, top_percent=0.20)
        assert len(result) == 1
        assert result[0].paper_id == "P1"

    def test_keeps_papers_at_threshold(self) -> None:
        papers = [
            _make_paper("P1", 2020, 100),
            _make_paper("P2", 2020, 100),
            _make_paper("P3", 2020, 50),
        ]
        result = filter_top_cited(papers, top_percent=0.50)
        assert len(result) == 2
        assert all(p.citation_count == 100 for p in result)

    def test_empty_input(self) -> None:
        result = filter_top_cited([], top_percent=0.20)
        assert result == []

    def test_multi_year_filtering(self) -> None:
        papers = [
            _make_paper("P1", 2020, 500),
            _make_paper("P2", 2020, 10),
            _make_paper("P3", 2021, 300),
            _make_paper("P4", 2021, 5),
        ]
        result = filter_top_cited(papers, top_percent=0.50)
        ids = {p.paper_id for p in result}
        assert ids == {"P1", "P3"}
