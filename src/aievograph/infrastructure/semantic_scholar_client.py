import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from aievograph.config.settings import AppSettings
from aievograph.domain.models import Author, Paper
from aievograph.domain.ports.paper_collector import PaperCollectorPort

logger = logging.getLogger(__name__)

_BULK_SEARCH_ENDPOINT = "/paper/search/bulk"
_FIELDS = "title,year,venue,citationCount,referenceCount,authors,externalIds,abstract"


def _parse_paper(raw: dict[str, Any]) -> Paper | None:
    """Convert a Semantic Scholar paper JSON to a Paper domain object.

    Returns None when required fields are missing.
    """
    paper_id = raw.get("paperId") or ""
    title = raw.get("title") or ""
    year = raw.get("year")
    if not paper_id or not title or year is None:
        return None

    authors = []
    for a in raw.get("authors") or []:
        aid = a.get("authorId") or ""
        aname = a.get("name") or ""
        if aid and aname:
            authors.append(Author(author_id=aid, name=aname))

    ext_ids = raw.get("externalIds") or {}
    ref_ids: tuple[str, ...] = ()
    if ext_ids.get("DBLP"):
        pass  # referenced_work_ids are populated via references endpoint later

    return Paper(
        paper_id=paper_id,
        title=title,
        publication_year=year,
        venue=raw.get("venue") or None,
        abstract=raw.get("abstract") or None,
        citation_count=raw.get("citationCount") or 0,
        reference_count=raw.get("referenceCount") or 0,
        referenced_work_ids=ref_ids,
        authors=authors,
    )


def _build_cache_key(venue: str, year_range: str, token: str) -> str:
    raw = f"{venue}:{year_range}:{token}"
    return hashlib.sha256(raw.encode()).hexdigest()


class SemanticScholarClient(PaperCollectorPort):
    """Infrastructure adapter that fetches papers from the Semantic Scholar Bulk API."""

    def __init__(self, settings: AppSettings) -> None:
        self._base_url = settings.s2_base_url.rstrip("/")
        self._api_key = settings.s2_api_key
        self._cache_dir = Path(settings.cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        path = self._cache_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def _write_cache(self, key: str, data: dict[str, Any]) -> None:
        path = self._cache_dir / f"{key}.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        venue: str,
        year_range: str,
        token: str,
    ) -> dict[str, Any]:
        cache_key = _build_cache_key(venue, year_range, token)
        cached = self._read_cache(cache_key)
        if cached is not None:
            logger.debug("Cache hit: venue=%s token=%s", venue, token[:12])
            return cached

        params: dict[str, str] = {
            "venue": venue,
            "year": year_range,
            "fields": _FIELDS,
        }
        if token:
            params["token"] = token

        resp = await client.get(
            f"{self._base_url}{_BULK_SEARCH_ENDPOINT}",
            params=params,
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        self._write_cache(cache_key, data)
        return data

    async def collect(
        self,
        venues: list[str],
        year_start: int,
        year_end: int,
    ) -> list[Paper]:
        """Collect all papers for given venues and year range via token-based pagination."""
        papers: list[Paper] = []
        year_range = f"{year_start}-{year_end}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            for venue in venues:
                token = ""
                page_num = 0
                while True:
                    page_num += 1
                    logger.info(
                        "Fetching venue=%s page=%d token=%s",
                        venue,
                        page_num,
                        token[:12] if token else "*",
                    )
                    data = await self._fetch_page(client, venue, year_range, token)

                    results = data.get("data", [])
                    if not results:
                        break

                    for raw_paper in results:
                        paper = _parse_paper(raw_paper)
                        if paper is not None:
                            papers.append(paper)

                    token = data.get("token") or ""
                    if not token:
                        break

                logger.info(
                    "Finished venue=%s total_collected=%d", venue, len(papers)
                )

        logger.info("Total papers collected: %d", len(papers))
        return papers
