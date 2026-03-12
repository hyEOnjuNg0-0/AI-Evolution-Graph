import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from aievograph.infrastructure.semantic_scholar_client import (
    SemanticScholarClient,
    _build_cache_key,
    _parse_paper,
)


def _make_settings(tmp_path: Any, top_percent: float = 1.0) -> Any:
    return type("S", (), {
        "s2_base_url": "https://api.semanticscholar.org/graph/v1",
        "s2_api_key": "",
        "cache_dir": str(tmp_path / "cache"),
        "citation_top_percent": top_percent,
    })()


def _make_raw_paper(
    *,
    paper_id: str = "abc123def456",
    title: str = "Test Paper",
    year: int = 2023,
    citation_count: int = 42,
    reference_count: int = 10,
    venue: str = "NeurIPS",
    authors: list[dict[str, Any]] | None = None,
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
    }


def _make_batch_response(
    paper_ids: list[str],
    refs_by_id: dict[str, list[str]] | None = None,
    abstract_by_id: dict[str, str | None] | None = None,
) -> list[dict[str, Any]]:
    """Build a POST /paper/batch style response list."""
    refs_by_id = refs_by_id or {}
    abstract_by_id = abstract_by_id or {}
    return [
        {
            "paperId": pid,
            "abstract": abstract_by_id.get(pid),
            "references": [{"paperId": r} for r in refs_by_id.get(pid, [])],
        }
        for pid in paper_ids
    ]


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
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "Alice"
        assert paper.authors[0].author_id == "100"
        # abstract and referenced_work_ids are always empty; populated via _fetch_batch
        assert paper.abstract is None
        assert paper.referenced_work_ids == ()

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
class TestFetchBatch:
    def _make_client(self, batch_response: list[dict[str, Any]]) -> Any:
        resp = AsyncMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: batch_response

        inst = AsyncMock()
        inst.post = AsyncMock(return_value=resp)
        return inst

    async def test_returns_abstract_and_refs(self, tmp_path: Any) -> None:
        s2 = SemanticScholarClient(_make_settings(tmp_path))  # type: ignore[arg-type]
        batch = _make_batch_response(
            ["P1"],
            refs_by_id={"P1": ["R1", "R2"]},
            abstract_by_id={"P1": "Test abstract."},
        )
        http = self._make_client(batch)

        result = await s2._fetch_batch(http, ["P1"])

        assert result["P1"]["abstract"] == "Test abstract."
        assert result["P1"]["referenced_work_ids"] == ("R1", "R2")

    async def test_skips_null_paper_id(self, tmp_path: Any) -> None:
        s2 = SemanticScholarClient(_make_settings(tmp_path))  # type: ignore[arg-type]
        resp_data = [{"paperId": None, "abstract": None, "references": []}]
        http = self._make_client(resp_data)

        result = await s2._fetch_batch(http, ["P1"])
        assert result == {}

    async def test_skips_null_ref_ids(self, tmp_path: Any) -> None:
        s2 = SemanticScholarClient(_make_settings(tmp_path))  # type: ignore[arg-type]
        resp_data = [{
            "paperId": "P1",
            "abstract": None,
            "references": [{"paperId": "R1"}, {"paperId": None}, {}],
        }]
        http = self._make_client(resp_data)

        result = await s2._fetch_batch(http, ["P1"])
        assert result["P1"]["referenced_work_ids"] == ("R1",)

    async def test_uses_cache(self, tmp_path: Any) -> None:
        s2 = SemanticScholarClient(_make_settings(tmp_path))  # type: ignore[arg-type]
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "batch_P1.json").write_text(
            json.dumps({"abstract": "cached", "referenced_work_ids": ["C1"]})
        )

        http = AsyncMock()
        http.post = AsyncMock()

        result = await s2._fetch_batch(http, ["P1"])
        assert result["P1"]["abstract"] == "cached"
        assert result["P1"]["referenced_work_ids"] == ["C1"]
        http.post.assert_not_called()


@pytest.mark.asyncio
class TestSemanticScholarClientCollect:
    def _make_mock_get_post(
        self,
        bulk_pages: list[dict],
        refs_by_id: dict[str, list[str]],
        abstract_by_id: dict[str, str | None] | None = None,
    ) -> tuple[Any, Any]:
        """Return (mock_get, mock_post) for bulk search and batch endpoint."""
        abstract_by_id = abstract_by_id or {}
        bulk_call = 0

        async def mock_get(url: str, **kwargs: Any) -> Any:
            nonlocal bulk_call
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            data = bulk_pages[bulk_call]
            bulk_call += 1
            resp.json = lambda d=data: d
            return resp

        async def mock_post(url: str, **kwargs: Any) -> Any:
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            ids = (kwargs.get("json") or {}).get("ids", [])
            resp.json = lambda: _make_batch_response(ids, refs_by_id, abstract_by_id)
            return resp

        return mock_get, mock_post

    def _patch_client(self, mock_get: Any, mock_post: Any) -> Any:
        inst = AsyncMock()
        inst.get = mock_get
        inst.post = mock_post
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=False)
        return inst

    async def test_collect_paginates_and_stops(self, tmp_path: Any) -> None:
        """collect() follows token pagination and stops when token is absent."""
        page1 = {"total": 2, "token": "next_token", "data": [_make_raw_paper(paper_id="P1")]}
        page2 = {"total": 2, "data": [_make_raw_paper(paper_id="P2")]}

        mock_get, mock_post = self._make_mock_get_post(
            [page1, page2],
            {"P1": ["R1"], "P2": ["R2"]},
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = self._patch_client(mock_get, mock_post)
            papers = await SemanticScholarClient(  # type: ignore[arg-type]
                _make_settings(tmp_path)
            ).collect(["NeurIPS"], 2020, 2023)

        assert len(papers) == 2
        assert {p.paper_id for p in papers} == {"P1", "P2"}
        assert any(p.referenced_work_ids == ("R1",) for p in papers)

    async def test_collect_populates_abstract_and_refs(self, tmp_path: Any) -> None:
        """abstract and referenced_work_ids are populated from _fetch_batch."""
        page = {"total": 1, "data": [_make_raw_paper(paper_id="P1")]}
        mock_get, mock_post = self._make_mock_get_post(
            [page],
            {"P1": ["ref_a", "ref_b"]},
            {"P1": "An interesting abstract."},
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = self._patch_client(mock_get, mock_post)
            papers = await SemanticScholarClient(  # type: ignore[arg-type]
                _make_settings(tmp_path)
            ).collect(["NeurIPS"], 2020, 2023)

        assert len(papers) == 1
        assert papers[0].referenced_work_ids == ("ref_a", "ref_b")
        assert papers[0].abstract == "An interesting abstract."

    async def test_collect_filters_before_fetching_batch(self, tmp_path: Any) -> None:
        """Only top-cited papers get a batch call."""
        page = {
            "total": 2,
            "data": [
                _make_raw_paper(paper_id="HIGH", citation_count=100),
                _make_raw_paper(paper_id="LOW", citation_count=1),
            ],
        }
        batch_call_ids: list[list[str]] = []

        async def mock_get(url: str, **kwargs: Any) -> Any:
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            resp.json = lambda: page
            return resp

        async def mock_post(url: str, **kwargs: Any) -> Any:
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            ids = (kwargs.get("json") or {}).get("ids", [])
            batch_call_ids.append(ids)
            resp.json = lambda: _make_batch_response(ids, {}, {})
            return resp

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.get = mock_get
            inst.post = mock_post
            inst.__aenter__ = AsyncMock(return_value=inst)
            inst.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = inst
            papers = await SemanticScholarClient(  # type: ignore[arg-type]
                _make_settings(tmp_path, top_percent=0.5)
            ).collect(["NeurIPS"], 2020, 2023)

        assert len(papers) == 1
        assert papers[0].paper_id == "HIGH"
        # LOW must not appear in any batch call
        all_ids = [pid for call in batch_call_ids for pid in call]
        assert "LOW" not in all_ids

    async def test_collect_uses_bulk_cache(self, tmp_path: Any) -> None:
        """Cached bulk pages are used without HTTP GET calls."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        cached_data = {"total": 1, "data": [_make_raw_paper(paper_id="P_CACHED")]}
        key = _build_cache_key("NeurIPS", "2020-2023", "")
        (cache_dir / f"{key}.json").write_text(json.dumps(cached_data))

        bulk_get_calls = 0

        async def mock_get(url: str, **kwargs: Any) -> Any:
            nonlocal bulk_get_calls
            bulk_get_calls += 1
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            resp.json = lambda: {}
            return resp

        async def mock_post(url: str, **kwargs: Any) -> Any:
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            ids = (kwargs.get("json") or {}).get("ids", [])
            resp.json = lambda: _make_batch_response(ids, {}, {})
            return resp

        settings = type("S", (), {
            "s2_base_url": "https://api.semanticscholar.org/graph/v1",
            "s2_api_key": "",
            "cache_dir": str(cache_dir),
            "citation_top_percent": 1.0,
        })()

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.get = mock_get
            inst.post = mock_post
            inst.__aenter__ = AsyncMock(return_value=inst)
            inst.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = inst
            papers = await SemanticScholarClient(settings).collect(  # type: ignore[arg-type]
                ["NeurIPS"], 2020, 2023
            )

        assert len(papers) == 1
        assert papers[0].paper_id == "P_CACHED"
        assert bulk_get_calls == 0

    async def test_collect_multiple_venues(self, tmp_path: Any) -> None:
        """collect() iterates over all venues."""
        pages = {
            "NeurIPS": {"total": 1, "data": [_make_raw_paper(paper_id="N1")]},
            "ICML": {"total": 1, "data": [_make_raw_paper(paper_id="I1")]},
        }

        async def mock_get(url: str, **kwargs: Any) -> Any:
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            venue = kwargs.get("params", {}).get("venue", "")
            resp.json = lambda v=venue: pages.get(v, {"total": 0, "data": []})
            return resp

        async def mock_post(url: str, **kwargs: Any) -> Any:
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            ids = (kwargs.get("json") or {}).get("ids", [])
            resp.json = lambda: _make_batch_response(ids, {}, {})
            return resp

        with patch("httpx.AsyncClient") as mock_cls:
            inst = AsyncMock()
            inst.get = mock_get
            inst.post = mock_post
            inst.__aenter__ = AsyncMock(return_value=inst)
            inst.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = inst
            papers = await SemanticScholarClient(  # type: ignore[arg-type]
                _make_settings(tmp_path)
            ).collect(["NeurIPS", "ICML"], 2020, 2023)

        assert {p.paper_id for p in papers} == {"N1", "I1"}
