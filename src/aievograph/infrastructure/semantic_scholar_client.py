"""
Semantic Scholar API
        ↓
SemanticScholarClient
        ↓
Bulk search (metadata) → per-page filter → references endpoint
        ↓
Return top-cited Paper objects with referenced_work_ids populated
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from aievograph.config.settings import AppSettings
from aievograph.domain.models import Author, Paper
from aievograph.domain.ports.paper_collector import PaperCollectorPort
from aievograph.domain.services.paper_filter import filter_top_cited

logger = logging.getLogger(__name__)

_BULK_SEARCH_ENDPOINT = "/paper/search/bulk"
_BATCH_ENDPOINT = "/paper/batch"
# abstract and references are not supported by the bulk search endpoint (HTTP 500);
# fetched via POST /paper/batch after per-page filtering.
_BULK_FIELDS = "title,year,venue,citationCount,referenceCount,authors"
_BATCH_FIELDS = "abstract,references"


def _parse_paper(raw: dict[str, Any]) -> Paper | None:
    """Convert a Semantic Scholar bulk search JSON entry to a Paper domain object.

    Returns None when required fields are missing.
    referenced_work_ids is always empty here; populated later via _fetch_references.
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

    return Paper(
        paper_id=paper_id,
        title=title,
        publication_year=year,
        venue=raw.get("venue") or None,
        citation_count=raw.get("citationCount") or 0,
        reference_count=raw.get("referenceCount") or 0,
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
        self._top_percent = settings.citation_top_percent

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    def _read_cache(self, key: str) -> Any | None:
        path = self._cache_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def _write_cache(self, key: str, data: Any) -> None:
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
            "fields": _BULK_FIELDS,
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

    async def _fetch_batch(
        self,
        client: httpx.AsyncClient,
        paper_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Fetch abstract and references for multiple papers via POST /paper/batch.

        Returns a mapping of paperId -> {abstract, referenced_work_ids}.
        Splits into chunks of 500 to stay within API limits.
        Results are cached individually per paper.
        """
        results: dict[str, dict[str, Any]] = {}
        uncached: list[str] = []

        for pid in paper_ids:
            cached = self._read_cache(f"batch_{pid}")
            if cached is not None:
                results[pid] = cached
            else:
                uncached.append(pid)

        chunk_size = 500
        for i in range(0, len(uncached), chunk_size):
            chunk = uncached[i : i + chunk_size]
            resp = await client.post(
                f"{self._base_url}{_BATCH_ENDPOINT}",
                params={"fields": _BATCH_FIELDS},
                json={"ids": chunk},
                headers=self._headers(),
            )
            resp.raise_for_status()
            for item in resp.json():
                pid = item.get("paperId") or ""
                if not pid:
                    continue
                ref_ids = tuple(
                    ref["paperId"]
                    for ref in item.get("references") or []
                    if ref.get("paperId")
                )
                entry: dict[str, Any] = {
                    "abstract": item.get("abstract") or None,
                    "referenced_work_ids": ref_ids,
                }
                self._write_cache(f"batch_{pid}", {
                    "abstract": entry["abstract"],
                    "referenced_work_ids": list(ref_ids),
                })
                results[pid] = entry

        return results

    async def collect(
        self,
        venues: list[str],
        year_start: int,
        year_end: int,
    ) -> list[Paper]:
        """Collect top-cited papers with their referenced_work_ids.

        Per page: bulk metadata → filter top citation_top_percent → fetch references.
        This minimises API calls by fetching references only for filtered papers.
        """
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

                    page_papers = [
                        p for raw in results
                        if (p := _parse_paper(raw)) is not None
                    ]

                    # Filter to top-cited papers before fetching references
                    filtered = filter_top_cited(page_papers, self._top_percent)
                    logger.info(
                        "venue=%s page=%d: %d → %d after filter",
                        venue, page_num, len(page_papers), len(filtered),
                    )

                    batch = await self._fetch_batch(client, [p.paper_id for p in filtered])
                    for paper in filtered:
                        extra = batch.get(paper.paper_id, {})
                        papers.append(paper.model_copy(update={
                            "abstract": extra.get("abstract"),
                            "referenced_work_ids": extra.get("referenced_work_ids", ()),
                        }))

                    token = data.get("token") or ""
                    if not token:
                        break

                logger.info(
                    "Finished venue=%s total_collected=%d", venue, len(papers)
                )

        logger.info("Total papers collected: %d", len(papers))
        return papers
