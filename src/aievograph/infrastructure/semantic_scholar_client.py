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
import logging
from pathlib import Path
from typing import Any

import httpx

from aievograph.config.settings import AppSettings
from aievograph.domain.models import Author, Paper
from aievograph.domain.ports.paper_collector import PaperCollectorPort
from aievograph.domain.utils.paper_filter import filter_top_cited
from aievograph.infrastructure.file_cache import (
    checkpoint_path,
    load_checkpoint,
    read_json,
    save_checkpoint,
    write_json,
)
from aievograph.infrastructure.http_utils import request_with_retry

logger = logging.getLogger(__name__)

_BULK_SEARCH_ENDPOINT = "/paper/search/bulk"
_BATCH_ENDPOINT = "/paper/batch"
# abstract and references are not supported by the bulk search endpoint (HTTP 500);
# fetched via POST /paper/batch after per-page filtering.
_BULK_FIELDS = "title,year,venue,citationCount,referenceCount,authors"
_BATCH_FIELDS = "abstract,references"
_S2_CHUNK_SIZE = 500  # S2 batch API limit per request


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

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        venue: str,
        year_range: str,
        token: str,
    ) -> dict[str, Any]:
        cache_key = _build_cache_key(venue, year_range, token)
        cached = read_json(self._cache_dir, cache_key)
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

        resp = await request_with_retry(
            client,
            "GET",
            f"{self._base_url}{_BULK_SEARCH_ENDPOINT}",
            params=params,
            headers=self._headers(),
        )
        data = resp.json()
        write_json(self._cache_dir, cache_key, data)
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
            cached = read_json(self._cache_dir, f"batch_{pid}")
            if cached is not None:
                results[pid] = cached
            else:
                uncached.append(pid)

        for i in range(0, len(uncached), _S2_CHUNK_SIZE):
            chunk = uncached[i : i + _S2_CHUNK_SIZE]
            resp = await request_with_retry(
                client,
                "POST",
                f"{self._base_url}{_BATCH_ENDPOINT}",
                params={"fields": _BATCH_FIELDS},
                json={"ids": chunk},
                headers=self._headers(),
            )
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
                write_json(self._cache_dir, f"batch_{pid}", {
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

        Resumes from a per-venue checkpoint if available, so re-runs skip
        already-completed venues. Each venue is saved to the checkpoint after
        all its pages are fetched and filtered.
        """
        year_range = f"{year_start}-{year_end}"
        ckpt_path = checkpoint_path(self._cache_dir, venues, year_range)
        checkpoint = load_checkpoint(ckpt_path)

        papers: list[Paper] = []

        # Restore papers from previously completed venues
        for venue, raw_papers in checkpoint.items():
            loaded = [Paper.model_validate(p) for p in raw_papers]
            papers.extend(loaded)
            logger.info(
                "Resumed venue=%s: loaded %d papers from checkpoint", venue, len(loaded)
            )

        async with httpx.AsyncClient(timeout=60.0) as client:
            for venue in venues:
                if venue in checkpoint:
                    logger.info("Skipping venue=%s (already in checkpoint)", venue)
                    continue

                venue_papers: list[Paper] = []
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
                        venue_papers.append(paper.model_copy(update={
                            "venue": venue,
                            "abstract": extra.get("abstract"),
                            "referenced_work_ids": tuple(extra.get("referenced_work_ids") or ()),
                        }))

                    token = data.get("token") or ""
                    if not token:
                        break

                # Save completed venue to checkpoint before moving to the next
                checkpoint[venue] = [p.model_dump() for p in venue_papers]
                save_checkpoint(ckpt_path, checkpoint)
                papers.extend(venue_papers)
                logger.info(
                    "Finished venue=%s total_collected=%d", venue, len(papers)
                )

        logger.info("Total papers collected: %d", len(papers))
        return papers
