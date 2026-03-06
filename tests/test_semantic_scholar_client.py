import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from aievograph.infrastructure.semantic_scholar_client import (
    SemanticScholarClient,
    _build_cache_key,
    _parse_paper,
)


def _make_raw_paper(
    *,
    paper_id: str = "abc123def456",
    title: str = "Test Paper",
    year: int = 2023,
    citation_count: int = 42,
    reference_count: int = 10,
    venue: str = "NeurIPS",
    authors: list[dict[str, Any]] | None = None,
    abstract: str | None = "An abstract.",
) -> dict[str, Any]:
    if authors is None:
        authors = [{"authorId": "100", "name": "Alice"}]
    return {
        "paperId": paper_id,
        "title": title,
        "year": year,
        "citationCount": citation_count,
        "referenceCount": reference_count,
        "venue": venue,
        "authors": authors,
        "abstract": abstract,
        "externalIds": {"DBLP": "conf/nips/Test23", "ArXiv": "2301.00001"},
    }


class TestParsePaper:
    def test_valid_paper(self) -> None:
        raw = _make_raw_paper()
        paper = _parse_paper(raw)
        assert paper is not None
        assert paper.paper_id == "abc123def456"
        assert paper.title == "Test Paper"
        assert paper.publication_year == 2023
        assert paper.citation_count == 42
        assert paper.reference_count == 10
        assert paper.venue == "NeurIPS"
        assert paper.abstract == "An abstract."
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "Alice"
        assert paper.authors[0].author_id == "100"

    def test_missing_paper_id_returns_none(self) -> None:
        raw = _make_raw_paper(paper_id="")
        assert _parse_paper(raw) is None

    def test_missing_title_returns_none(self) -> None:
        raw = _make_raw_paper(title="")
        assert _parse_paper(raw) is None

    def test_missing_year_returns_none(self) -> None:
        raw = _make_raw_paper()
        raw["year"] = None
        assert _parse_paper(raw) is None

    def test_null_venue(self) -> None:
        raw = _make_raw_paper(venue="")
        paper = _parse_paper(raw)
        assert paper is not None
        assert paper.venue is None

    def test_null_abstract(self) -> None:
        raw = _make_raw_paper(abstract=None)
        paper = _parse_paper(raw)
        assert paper is not None
        assert paper.abstract is None

    def test_empty_authors(self) -> None:
        raw = _make_raw_paper(authors=[])
        paper = _parse_paper(raw)
        assert paper is not None
        assert paper.authors == []

    def test_author_missing_id_skipped(self) -> None:
        raw = _make_raw_paper(authors=[
            {"authorId": "", "name": "Bob"},
            {"authorId": "200", "name": "Carol"},
        ])
        paper = _parse_paper(raw)
        assert paper is not None
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "Carol"


@pytest.mark.asyncio
class TestSemanticScholarClientCollect:
    async def test_collect_paginates_and_stops(self, tmp_path: Any) -> None:
        """Verify that collect follows token pagination and stops when token is absent."""
        page1 = {
            "total": 2,
            "token": "next_page_token",
            "data": [_make_raw_paper(paper_id="P1")],
        }
        page2 = {
            "total": 2,
            "data": [_make_raw_paper(paper_id="P2")],
        }

        settings = type("S", (), {
            "s2_base_url": "https://api.semanticscholar.org/graph/v1",
            "s2_api_key": "",
            "cache_dir": str(tmp_path / "cache"),
        })()

        client = SemanticScholarClient(settings)  # type: ignore[arg-type]

        call_count = 0
        pages = [page1, page2]

        async def mock_get(url: str, **kwargs: Any) -> Any:
            nonlocal call_count
            data = pages[call_count]
            call_count += 1
            resp = AsyncMock()
            resp.json = lambda: data
            resp.raise_for_status = lambda: None
            return resp

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.get = mock_get
            inst.__aenter__ = AsyncMock(return_value=inst)
            inst.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = inst

            papers = await client.collect(["NeurIPS"], 2020, 2023)

        assert len(papers) == 2
        assert papers[0].paper_id == "P1"
        assert papers[1].paper_id == "P2"
        assert call_count == 2

    async def test_collect_uses_cache(self, tmp_path: Any) -> None:
        """Verify that cached responses are used instead of making HTTP calls."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        cached_data = {
            "total": 1,
            "data": [_make_raw_paper(paper_id="P_CACHED")],
        }
        key = _build_cache_key("NeurIPS", "2020-2023", "")
        (cache_dir / f"{key}.json").write_text(json.dumps(cached_data))

        settings = type("S", (), {
            "s2_base_url": "https://api.semanticscholar.org/graph/v1",
            "s2_api_key": "",
            "cache_dir": str(cache_dir),
        })()

        client = SemanticScholarClient(settings)  # type: ignore[arg-type]

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.get = AsyncMock()
            inst.__aenter__ = AsyncMock(return_value=inst)
            inst.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = inst

            papers = await client.collect(["NeurIPS"], 2020, 2023)

        assert len(papers) == 1
        assert papers[0].paper_id == "P_CACHED"
        inst.get.assert_not_called()

    async def test_collect_multiple_venues(self, tmp_path: Any) -> None:
        """Verify that collect iterates over multiple venues."""
        def make_page(pid: str) -> dict[str, Any]:
            return {"total": 1, "data": [_make_raw_paper(paper_id=pid)]}

        settings = type("S", (), {
            "s2_base_url": "https://api.semanticscholar.org/graph/v1",
            "s2_api_key": "",
            "cache_dir": str(tmp_path / "cache"),
        })()

        client = SemanticScholarClient(settings)  # type: ignore[arg-type]

        call_count = 0
        venue_pages = {"NeurIPS": make_page("N1"), "ICML": make_page("I1")}

        async def mock_get(url: str, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            params = kwargs.get("params", {})
            venue = params.get("venue", "")
            data = venue_pages.get(venue, {"total": 0, "data": []})
            resp = AsyncMock()
            resp.json = lambda: data
            resp.raise_for_status = lambda: None
            return resp

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.get = mock_get
            inst.__aenter__ = AsyncMock(return_value=inst)
            inst.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = inst

            papers = await client.collect(["NeurIPS", "ICML"], 2020, 2023)

        assert len(papers) == 2
        assert {p.paper_id for p in papers} == {"N1", "I1"}
