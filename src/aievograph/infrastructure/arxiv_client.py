"""
arXiv API (Atom XML)  →  paper discovery by category
Semantic Scholar API  →  citation count + reference enrichment

ArxivClient.collect(categories, year_start, year_end)
      ↓
 1. Paginate arXiv search per category → collect arXiv IDs (up to max_papers limit)
    (checkpoint saved per category; completed categories are skipped on re-run)
 2. Deduplicate across categories
 3. POST S2 /paper/batch (ArXiv:<id>) → citation counts → filter_top_cited
 4. POST S2 /paper/batch (S2 paperId)  → abstract + references for filtered papers only
      ↓
Return Paper objects with referenced_work_ids populated
"""

import asyncio
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
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

_ARXIV_API_URL = "https://export.arxiv.org/api/query"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"

_S2_BATCH_ENDPOINT = "/paper/batch"
# Pass 1: citation counts only (cheap) — references fetched only for top-cited papers
_S2_CITATION_FIELDS = "paperId,title,year,citationCount,referenceCount,externalIds,authors"
_S2_DETAIL_FIELDS = "abstract,references"

_ARXIV_PAGE_SIZE = 500    # arXiv API recommended max per request
_S2_CHUNK_SIZE = 500      # S2 batch limit
_ARXIV_REQUEST_DELAY = 3.0  # seconds between arXiv requests (per API guidelines)


def _extract_arxiv_id(entry_id: str) -> str | None:
    """Extract base arXiv ID from entry URL (e.g. 'http://arxiv.org/abs/2301.12345v2' → '2301.12345')."""
    match = re.search(r"abs/(\d{4}\.\d{4,5})", entry_id)
    return match.group(1) if match else None


def parse_arxiv_feed(xml_text: str, year_start: int, year_end: int) -> list[dict[str, Any]]:
    """Parse arXiv Atom XML feed into entry dicts, filtered to [year_start, year_end].

    Returns list of dicts with: arxiv_id, title, year, abstract, authors (list of name strings).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("Failed to parse arXiv XML: %s", exc)
        return []

    entries: list[dict[str, Any]] = []
    for entry in root.findall(f"{_ATOM_NS}entry"):
        id_el = entry.find(f"{_ATOM_NS}id")
        if id_el is None or not id_el.text:
            continue
        arxiv_id = _extract_arxiv_id(id_el.text)
        if not arxiv_id:
            continue

        published_el = entry.find(f"{_ATOM_NS}published")
        year: int | None = None
        if published_el is not None and published_el.text:
            try:
                year = int(published_el.text[:4])
            except ValueError:
                pass
        if year is None or not (year_start <= year <= year_end):
            continue

        title_el = entry.find(f"{_ATOM_NS}title")
        title = " ".join((title_el.text or "").split()) if title_el is not None else ""

        summary_el = entry.find(f"{_ATOM_NS}summary")
        abstract = " ".join((summary_el.text or "").split()) if summary_el is not None else None

        authors: list[str] = []
        for author_el in entry.findall(f"{_ATOM_NS}author"):
            name_el = author_el.find(f"{_ATOM_NS}name")
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        entries.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "year": year,
            "abstract": abstract or None,
            "authors": authors,
        })

    return entries


class ArxivClient(PaperCollectorPort):
    """Collects arXiv preprints by category, enriched with Semantic Scholar citation data.

    The `venues` parameter in collect() is interpreted as arXiv subject categories
    (e.g. ["cs.AI", "cs.LG", "cs.CL"]).
    """

    def __init__(self, settings: AppSettings) -> None:
        self._s2_base_url = settings.s2_base_url.rstrip("/")
        self._s2_api_key = settings.s2_api_key
        self._cache_dir = Path(settings.cache_dir).parent / "arxiv"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._top_percent = settings.citation_top_percent
        self._max_papers = settings.arxiv_max_papers_per_category

    def _s2_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._s2_api_key:
            headers["x-api-key"] = self._s2_api_key
        return headers

    def _cache_key(self, *parts: str) -> str:
        return hashlib.sha256(":".join(parts).encode()).hexdigest()

    async def _fetch_arxiv_page(
        self,
        client: httpx.AsyncClient,
        category: str,
        year_start: int,
        year_end: int,
        start: int,
    ) -> list[dict[str, Any]]:
        """Fetch one paginated page of arXiv entries for a category and year range."""
        key = self._cache_key("page", category, f"{year_start}-{year_end}", str(start))
        cached = read_json(self._cache_dir, key)
        if cached is not None:
            logger.debug("Cache hit: arXiv category=%s start=%d", category, start)
            return cached

        # arXiv submittedDate filter format: YYYYMMDD (no wildcards)
        date_query = f"submittedDate:[{year_start}0101 TO {year_end}1231]"
        params: dict[str, Any] = {
            "search_query": f"cat:{category} AND {date_query}",
            "start": start,
            "max_results": _ARXIV_PAGE_SIZE,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        resp = await client.get(_ARXIV_API_URL, params=params)
        resp.raise_for_status()
        entries = parse_arxiv_feed(resp.text, year_start, year_end)
        write_json(self._cache_dir, key, entries)
        return entries

    async def _fetch_s2_citations(
        self,
        client: httpx.AsyncClient,
        arxiv_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Fetch S2 paper IDs and citation counts for arXiv IDs.

        Sends 'ArXiv:<id>' format IDs to S2 batch endpoint.
        Returns mapping: arxiv_id -> {paper_id, title, year, citation_count,
                                      reference_count, authors}.
        """
        results: dict[str, dict[str, Any]] = {}
        uncached: list[str] = []

        for arxiv_id in arxiv_ids:
            cached = read_json(self._cache_dir, f"cite_{arxiv_id}")
            if cached is not None:
                results[arxiv_id] = cached
            else:
                uncached.append(arxiv_id)

        for i in range(0, len(uncached), _S2_CHUNK_SIZE):
            chunk = uncached[i : i + _S2_CHUNK_SIZE]
            s2_ids = [f"ArXiv:{aid}" for aid in chunk]

            resp = await request_with_retry(
                client,
                "POST",
                f"{self._s2_base_url}{_S2_BATCH_ENDPOINT}",
                params={"fields": _S2_CITATION_FIELDS},
                json={"ids": s2_ids},
                headers=self._s2_headers(),
            )

            for item in resp.json():
                if not item:  # S2 returns null for papers it cannot find
                    continue
                paper_id = item.get("paperId") or ""
                if not paper_id:
                    continue
                ext_ids = item.get("externalIds") or {}
                arxiv_id = ext_ids.get("ArXiv") or ""
                if not arxiv_id:
                    continue

                entry: dict[str, Any] = {
                    "paper_id": paper_id,
                    "title": item.get("title") or "",
                    "year": item.get("year"),
                    "citation_count": item.get("citationCount") or 0,
                    "reference_count": item.get("referenceCount") or 0,
                    "authors": item.get("authors") or [],
                }
                write_json(self._cache_dir, f"cite_{arxiv_id}", entry)
                results[arxiv_id] = entry

        return results

    async def _fetch_s2_details(
        self,
        client: httpx.AsyncClient,
        paper_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Fetch abstract and references for S2 paper IDs (post-filter, top-cited papers only).

        Returns mapping: paper_id -> {abstract, referenced_work_ids}.
        """
        results: dict[str, dict[str, Any]] = {}
        uncached: list[str] = []

        for pid in paper_ids:
            cached = read_json(self._cache_dir, f"detail_{pid}")
            if cached is not None:
                results[pid] = cached
            else:
                uncached.append(pid)

        for i in range(0, len(uncached), _S2_CHUNK_SIZE):
            chunk = uncached[i : i + _S2_CHUNK_SIZE]
            resp = await request_with_retry(
                client,
                "POST",
                f"{self._s2_base_url}{_S2_BATCH_ENDPOINT}",
                params={"fields": _S2_DETAIL_FIELDS},
                json={"ids": chunk},
                headers=self._s2_headers(),
            )

            for item in resp.json():
                if not item:
                    continue
                pid = item.get("paperId") or ""
                if not pid:
                    continue
                ref_ids = tuple(
                    ref["paperId"]
                    for ref in item.get("references") or []
                    if ref.get("paperId")
                )
                entry = {
                    "abstract": item.get("abstract") or None,
                    "referenced_work_ids": list(ref_ids),
                }
                write_json(self._cache_dir, f"detail_{pid}", entry)
                results[pid] = entry

        return results

    async def collect(
        self,
        venues: list[str],
        year_start: int,
        year_end: int,
    ) -> list[Paper]:
        """Collect top-cited arXiv preprints by category.

        `venues` is interpreted as arXiv subject categories (e.g. ["cs.AI", "cs.LG"]).
        Per-category arXiv entries are checkpointed, so re-runs skip completed categories.
        Papers from multiple categories are deduplicated by arXiv ID before S2 enrichment,
        minimising API calls.
        """
        year_range = f"{year_start}-{year_end}"
        ckpt_path = checkpoint_path(self._cache_dir, venues, year_range)
        checkpoint = load_checkpoint(ckpt_path)

        # --- Step 1: collect arXiv entries across all categories ---
        entries_by_id: dict[str, dict[str, Any]] = {}

        # Restore completed categories from checkpoint
        for category, entries in checkpoint.items():
            for e in entries:
                if e["arxiv_id"] not in entries_by_id:
                    entries_by_id[e["arxiv_id"]] = e
            logger.info(
                "Resumed category=%s: loaded %d entries from checkpoint", category, len(entries)
            )

        async with httpx.AsyncClient(timeout=60.0) as client:
            for category in venues:
                if category in checkpoint:
                    logger.info("Skipping category=%s (already in checkpoint)", category)
                    continue

                logger.info(
                    "Fetching arXiv category=%s years=%d-%d", category, year_start, year_end
                )
                start = 0
                category_count = 0
                category_entries: list[dict[str, Any]] = []

                while category_count < self._max_papers:
                    entries = await self._fetch_arxiv_page(
                        client, category, year_start, year_end, start
                    )
                    if not entries:
                        break

                    new = 0
                    for e in entries:
                        category_entries.append(e)
                        if e["arxiv_id"] not in entries_by_id:
                            entries_by_id[e["arxiv_id"]] = e
                            new += 1
                    category_count += len(entries)

                    logger.info(
                        "category=%s start=%d fetched=%d new=%d total_unique=%d",
                        category, start, len(entries), new, len(entries_by_id),
                    )

                    if len(entries) < _ARXIV_PAGE_SIZE:
                        break
                    start += _ARXIV_PAGE_SIZE
                    await asyncio.sleep(_ARXIV_REQUEST_DELAY)

                # Save completed category to checkpoint
                checkpoint[category] = category_entries
                save_checkpoint(ckpt_path, checkpoint)

            if not entries_by_id:
                logger.warning("No arXiv entries found for categories=%s", venues)
                return []

            logger.info("Unique arXiv entries collected: %d", len(entries_by_id))

            # --- Step 2: enrich with S2 citation counts ---
            arxiv_ids = list(entries_by_id.keys())
            citations = await self._fetch_s2_citations(client, arxiv_ids)
            logger.info("S2 matched %d / %d arXiv entries", len(citations), len(arxiv_ids))

            # Build Paper objects (no references yet) for citation-based filtering
            pre_filter: list[Paper] = []
            paper_to_arxiv: dict[str, str] = {}  # s2 paper_id → arxiv_id

            for arxiv_id, cite in citations.items():
                paper_id = cite.get("paper_id") or ""
                title = cite.get("title") or ""
                year = cite.get("year")
                if not paper_id or not title or year is None:
                    continue

                authors: list[Author] = []
                for a in cite.get("authors") or []:
                    aid = a.get("authorId") or ""
                    aname = a.get("name") or ""
                    if aid and aname:
                        authors.append(Author(author_id=aid, name=aname))

                original = entries_by_id[arxiv_id]
                pre_filter.append(Paper(
                    paper_id=paper_id,
                    title=title,
                    publication_year=year,
                    venue=None,
                    citation_count=cite.get("citation_count") or 0,
                    reference_count=cite.get("reference_count") or 0,
                    abstract=original.get("abstract"),
                    authors=authors,
                ))
                paper_to_arxiv[paper_id] = arxiv_id

            # --- Step 3: filter to top-cited papers ---
            filtered = filter_top_cited(pre_filter, self._top_percent)
            logger.info(
                "arXiv filter: %d → %d (top %.0f%%)",
                len(pre_filter), len(filtered), self._top_percent * 100,
            )

            if not filtered:
                return []

            # --- Step 4: fetch abstract + references for filtered papers only ---
            details = await self._fetch_s2_details(client, [p.paper_id for p in filtered])

            papers: list[Paper] = []
            for paper in filtered:
                detail = details.get(paper.paper_id, {})
                abstract = detail.get("abstract") or paper.abstract
                ref_ids = tuple(detail.get("referenced_work_ids") or ())
                papers.append(paper.model_copy(update={
                    "abstract": abstract,
                    "referenced_work_ids": ref_ids,
                }))

        logger.info("Total arXiv papers collected: %d", len(papers))
        return papers
