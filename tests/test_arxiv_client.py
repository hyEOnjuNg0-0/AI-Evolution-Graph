import json
from textwrap import dedent
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from aievograph.infrastructure.arxiv_client import ArxivClient, parse_arxiv_feed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(tmp_path: Any, top_percent: float = 1.0, max_papers: int = 10_000) -> Any:
    return type("S", (), {
        "s2_base_url": "https://api.semanticscholar.org/graph/v1",
        "s2_api_key": "",
        "cache_dir": str(tmp_path / "semantic_scholar"),
        "citation_top_percent": top_percent,
        "arxiv_max_papers_per_category": max_papers,
    })()


def _make_atom_feed(entries: list[dict[str, Any]]) -> str:
    """Build a minimal arXiv Atom XML feed string from entry dicts."""
    items = ""
    for e in entries:
        authors_xml = "".join(
            f"<author><name>{a}</name></author>" for a in e.get("authors", [])
        )
        items += dedent(f"""\
            <entry>
              <id>http://arxiv.org/abs/{e["arxiv_id"]}v1</id>
              <title>{e["title"]}</title>
              <summary>{e.get("abstract", "")}</summary>
              <published>{e["year"]}-06-15T00:00:00Z</published>
              {authors_xml}
            </entry>
        """)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        f"{items}</feed>"
    )


def _make_s2_citation_response(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a S2 POST /paper/batch response for citation-count pass."""
    return [
        {
            "paperId": e["paper_id"],
            "title": e["title"],
            "year": e["year"],
            "citationCount": e.get("citation_count", 0),
            "referenceCount": e.get("reference_count", 0),
            "externalIds": {"ArXiv": e["arxiv_id"]},
            "authors": [{"authorId": f"a{i}", "name": n}
                        for i, n in enumerate(e.get("authors", []))],
        }
        for e in entries
    ]


def _make_s2_detail_response(
    paper_ids: list[str],
    refs_by_id: dict[str, list[str]] | None = None,
    abstract_by_id: dict[str, str | None] | None = None,
) -> list[dict[str, Any]]:
    """Build a S2 POST /paper/batch response for abstract + references pass."""
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


# ---------------------------------------------------------------------------
# parse_arxiv_feed
# ---------------------------------------------------------------------------

class TestParseArxivFeed:
    def test_valid_entry(self) -> None:
        feed = _make_atom_feed([{
            "arxiv_id": "2301.12345",
            "title": "Test Paper",
            "year": 2023,
            "abstract": "An abstract.",
            "authors": ["Alice", "Bob"],
        }])
        entries = parse_arxiv_feed(feed, 2020, 2025)
        assert len(entries) == 1
        e = entries[0]
        assert e["arxiv_id"] == "2301.12345"
        assert e["title"] == "Test Paper"
        assert e["year"] == 2023
        assert e["abstract"] == "An abstract."
        assert e["authors"] == ["Alice", "Bob"]

    def test_filters_out_of_range_year(self) -> None:
        feed = _make_atom_feed([
            {"arxiv_id": "2001.00001", "title": "Old", "year": 2000, "authors": []},
            {"arxiv_id": "2301.00002", "title": "New", "year": 2023, "authors": []},
        ])
        entries = parse_arxiv_feed(feed, 2020, 2025)
        assert len(entries) == 1
        assert entries[0]["arxiv_id"] == "2301.00002"

    def test_skips_entry_without_id(self) -> None:
        xml = (
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<entry><title>No ID</title>"
            "<published>2023-01-01T00:00:00Z</published></entry>"
            "</feed>"
        )
        assert parse_arxiv_feed(xml, 2020, 2025) == []

    def test_malformed_xml_returns_empty(self) -> None:
        assert parse_arxiv_feed("not xml at all", 2020, 2025) == []

    def test_versioned_id_stripped(self) -> None:
        feed = _make_atom_feed([
            {"arxiv_id": "2301.12345", "title": "T", "year": 2023, "authors": []}
        ])
        # The helper already appends 'v1'; verify the ID is stripped correctly
        entries = parse_arxiv_feed(feed, 2020, 2025)
        assert entries[0]["arxiv_id"] == "2301.12345"


# ---------------------------------------------------------------------------
# ArxivClient — _fetch_s2_citations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestFetchS2Citations:
    def _make_client(self, post_response: list[dict]) -> Any:
        resp = AsyncMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: post_response

        inst = AsyncMock()
        inst.post = AsyncMock(return_value=resp)
        return inst

    async def test_returns_citation_data(self, tmp_path: Any) -> None:
        client = ArxivClient(_make_settings(tmp_path))  # type: ignore[arg-type]
        s2_resp = _make_s2_citation_response([{
            "arxiv_id": "2301.12345",
            "paper_id": "S2ID1",
            "title": "My Paper",
            "year": 2023,
            "citation_count": 50,
            "reference_count": 30,
            "authors": ["Alice"],
        }])
        http = self._make_client(s2_resp)

        result = await client._fetch_s2_citations(http, ["2301.12345"])

        assert "2301.12345" in result
        assert result["2301.12345"]["paper_id"] == "S2ID1"
        assert result["2301.12345"]["citation_count"] == 50

    async def test_skips_null_items(self, tmp_path: Any) -> None:
        client = ArxivClient(_make_settings(tmp_path))  # type: ignore[arg-type]
        http = self._make_client([None])  # S2 returns null for unknown papers

        result = await client._fetch_s2_citations(http, ["9999.99999"])
        assert result == {}

    async def test_uses_cache(self, tmp_path: Any) -> None:
        client = ArxivClient(_make_settings(tmp_path))  # type: ignore[arg-type]
        cache_dir = tmp_path / "arxiv"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached_entry = {"paper_id": "CACHED", "title": "T", "year": 2022,
                        "citation_count": 10, "reference_count": 5, "authors": []}
        # _read_cache uses the key as-is for the filename (no hashing at this level)
        (cache_dir / "cite_2301.11111.json").write_text(json.dumps(cached_entry))

        http = AsyncMock()
        http.post = AsyncMock()

        result = await client._fetch_s2_citations(http, ["2301.11111"])
        assert result["2301.11111"]["paper_id"] == "CACHED"
        http.post.assert_not_called()


# ---------------------------------------------------------------------------
# ArxivClient — _fetch_s2_details
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestFetchS2Details:
    def _make_client(self, post_response: list[dict]) -> Any:
        resp = AsyncMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: post_response

        inst = AsyncMock()
        inst.post = AsyncMock(return_value=resp)
        return inst

    async def test_returns_abstract_and_refs(self, tmp_path: Any) -> None:
        client = ArxivClient(_make_settings(tmp_path))  # type: ignore[arg-type]
        s2_resp = _make_s2_detail_response(
            ["S2ID1"],
            refs_by_id={"S2ID1": ["R1", "R2"]},
            abstract_by_id={"S2ID1": "Great abstract."},
        )
        http = self._make_client(s2_resp)

        result = await client._fetch_s2_details(http, ["S2ID1"])

        assert result["S2ID1"]["abstract"] == "Great abstract."
        assert result["S2ID1"]["referenced_work_ids"] == ["R1", "R2"]

    async def test_skips_null_ref_paper_ids(self, tmp_path: Any) -> None:
        client = ArxivClient(_make_settings(tmp_path))  # type: ignore[arg-type]
        s2_resp = [{
            "paperId": "S2ID1",
            "abstract": None,
            "references": [{"paperId": "R1"}, {"paperId": None}, {}],
        }]
        http = self._make_client(s2_resp)

        result = await client._fetch_s2_details(http, ["S2ID1"])
        assert result["S2ID1"]["referenced_work_ids"] == ["R1"]


# ---------------------------------------------------------------------------
# ArxivClient.collect — end-to-end with mocked HTTP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestArxivClientCollect:
    def _patch_client(
        self,
        arxiv_xml: str,
        s2_cite_response: list[dict],
        s2_detail_response: list[dict],
    ) -> Any:
        arxiv_get_call = 0

        async def mock_get(url: str, **kwargs: Any) -> Any:
            nonlocal arxiv_get_call
            arxiv_get_call += 1
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            resp.text = arxiv_xml
            return resp

        post_call = 0

        async def mock_post(url: str, **kwargs: Any) -> Any:
            nonlocal post_call
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            if post_call == 0:
                resp.json = lambda: s2_cite_response
            else:
                resp.json = lambda: s2_detail_response
            post_call += 1
            return resp

        inst = AsyncMock()
        inst.get = mock_get
        inst.post = mock_post
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=False)
        return inst

    async def test_collect_returns_papers(self, tmp_path: Any) -> None:
        feed = _make_atom_feed([{
            "arxiv_id": "2301.12345",
            "title": "Test Paper",
            "year": 2023,
            "authors": ["Alice"],
        }])
        s2_cite = _make_s2_citation_response([{
            "arxiv_id": "2301.12345", "paper_id": "S2ID1",
            "title": "Test Paper", "year": 2023,
            "citation_count": 100, "reference_count": 20, "authors": ["Alice"],
        }])
        s2_detail = _make_s2_detail_response(
            ["S2ID1"],
            refs_by_id={"S2ID1": ["R1"]},
            abstract_by_id={"S2ID1": "The abstract."},
        )

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = self._patch_client(feed, s2_cite, s2_detail)
            papers = await ArxivClient(  # type: ignore[arg-type]
                _make_settings(tmp_path)
            ).collect(["cs.LG"], 2020, 2023)

        assert len(papers) == 1
        assert papers[0].paper_id == "S2ID1"
        assert papers[0].title == "Test Paper"
        assert papers[0].venue is None
        assert papers[0].referenced_work_ids == ("R1",)
        assert papers[0].abstract == "The abstract."

    async def test_deduplicates_across_categories(self, tmp_path: Any) -> None:
        """Same arXiv ID appearing in multiple categories is collected only once."""
        feed = _make_atom_feed([{
            "arxiv_id": "2301.12345", "title": "Shared", "year": 2023, "authors": [],
        }])
        s2_cite = _make_s2_citation_response([{
            "arxiv_id": "2301.12345", "paper_id": "S2ID1",
            "title": "Shared", "year": 2023,
            "citation_count": 10, "reference_count": 5, "authors": [],
        }])
        s2_detail = _make_s2_detail_response(["S2ID1"])

        post_call = 0
        get_call = 0

        async def mock_get(url: str, **kwargs: Any) -> Any:
            nonlocal get_call
            get_call += 1
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            resp.text = feed
            return resp

        async def mock_post(url: str, **kwargs: Any) -> Any:
            nonlocal post_call
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            # Capture current post_call value before incrementing
            resp.json = lambda r=(s2_cite if post_call == 0 else s2_detail): r
            post_call += 1
            return resp

        inst = AsyncMock()
        inst.get = mock_get
        inst.post = mock_post
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = inst
            papers = await ArxivClient(  # type: ignore[arg-type]
                _make_settings(tmp_path)
            ).collect(["cs.AI", "cs.LG"], 2020, 2023)

        assert len(papers) == 1
        # S2 citation batch should be called only once (after deduplication)
        assert post_call == 2  # once for citations, once for details

    async def test_filters_before_fetching_details(self, tmp_path: Any) -> None:
        """Only top-cited papers trigger the S2 details batch call."""
        feed = _make_atom_feed([
            {"arxiv_id": "2301.00001", "title": "High", "year": 2023, "authors": []},
            {"arxiv_id": "2301.00002", "title": "Low", "year": 2023, "authors": []},
        ])
        s2_cite = _make_s2_citation_response([
            {"arxiv_id": "2301.00001", "paper_id": "HIGH",
             "title": "High", "year": 2023, "citation_count": 200, "authors": []},
            {"arxiv_id": "2301.00002", "paper_id": "LOW",
             "title": "Low", "year": 2023, "citation_count": 1, "authors": []},
        ])
        detail_call_ids: list[list[str]] = []

        async def mock_get(url: str, **kwargs: Any) -> Any:
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            resp.text = feed
            return resp

        post_call = 0

        async def mock_post(url: str, **kwargs: Any) -> Any:
            nonlocal post_call
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            ids = (kwargs.get("json") or {}).get("ids", [])
            if post_call == 0:
                resp.json = lambda: s2_cite
            else:
                detail_call_ids.append(ids)
                resp.json = lambda: _make_s2_detail_response(ids)
            post_call += 1
            return resp

        inst = AsyncMock()
        inst.get = mock_get
        inst.post = mock_post
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = inst
            papers = await ArxivClient(  # type: ignore[arg-type]
                _make_settings(tmp_path, top_percent=0.5)
            ).collect(["cs.LG"], 2020, 2023)

        assert len(papers) == 1
        assert papers[0].paper_id == "HIGH"
        all_detail_ids = [pid for call in detail_call_ids for pid in call]
        assert "LOW" not in all_detail_ids

    async def test_returns_empty_when_no_arxiv_entries(self, tmp_path: Any) -> None:
        empty_feed = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'

        async def mock_get(url: str, **kwargs: Any) -> Any:
            resp = AsyncMock()
            resp.raise_for_status = lambda: None
            resp.text = empty_feed
            return resp

        inst = AsyncMock()
        inst.get = mock_get
        inst.__aenter__ = AsyncMock(return_value=inst)
        inst.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = inst
            papers = await ArxivClient(  # type: ignore[arg-type]
                _make_settings(tmp_path)
            ).collect(["cs.LG"], 2020, 2023)

        assert papers == []
