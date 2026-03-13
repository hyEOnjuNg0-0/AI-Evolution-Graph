"""arXiv + Semantic Scholar 데이터 확인용 스크립트.

ArxivClient의 실제 수집 흐름을 단계별로 재현하여 각 API 응답을 검증.

사용법:
  python check_arxiv_data.py                      # 기본: cs.LG 2023, top 3
  python check_arxiv_data.py cs.AI 2024           # 카테고리/연도 지정
  python check_arxiv_data.py cs.CV 2023 5         # 결과 건수 지정
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import json
import re
import xml.etree.ElementTree as ET
import httpx

CATEGORY = sys.argv[1] if len(sys.argv) > 1 else "cs.LG"
YEAR     = int(sys.argv[2]) if len(sys.argv) > 2 else 2023
LIMIT    = int(sys.argv[3]) if len(sys.argv) > 3 else 3

ARXIV_URL = "https://export.arxiv.org/api/query"
S2_BASE   = "https://api.semanticscholar.org/graph/v1"
ATOM_NS   = "{http://www.w3.org/2005/Atom}"

client = httpx.Client(timeout=30)

# ── Step 1: arXiv API ──────────────────────────────────────────────────────
print("=" * 80)
print(f"STEP 1 — arXiv API  category={CATEGORY}  year={YEAR}  limit={LIMIT}")
print("=" * 80)

date_query = f"submittedDate:[{YEAR}0101 TO {YEAR}1231]"
r = client.get(ARXIV_URL, params={
    "search_query": f"cat:{CATEGORY} AND {date_query}",
    "start": 0,
    "max_results": LIMIT * 5,   # fetch extra to have enough after year filter
    "sortBy": "submittedDate",
    "sortOrder": "descending",
})
r.raise_for_status()

root = ET.fromstring(r.text)
entries = []
for entry in root.findall(f"{ATOM_NS}entry"):
    id_el = entry.find(f"{ATOM_NS}id")
    if id_el is None or not id_el.text:
        continue
    m = re.search(r"abs/(\d{4}\.\d{4,5})", id_el.text)
    if not m:
        continue
    arxiv_id = m.group(1)

    pub_el = entry.find(f"{ATOM_NS}published")
    year = int(pub_el.text[:4]) if pub_el is not None and pub_el.text else None
    if year != YEAR:
        continue

    title_el = entry.find(f"{ATOM_NS}title")
    title = " ".join((title_el.text or "").split()) if title_el is not None else ""

    authors = []
    for a in entry.findall(f"{ATOM_NS}author"):
        n = a.find(f"{ATOM_NS}name")
        if n is not None and n.text:
            authors.append(n.text.strip())

    entries.append({"arxiv_id": arxiv_id, "title": title, "year": year, "authors": authors})
    if len(entries) >= LIMIT:
        break

print(f"arXiv entries returned (year={YEAR}): {len(entries)}\n")
for i, e in enumerate(entries, 1):
    print(f"[{i}] arXiv:{e['arxiv_id']}")
    print(f"     title   : {e['title']}")
    print(f"     year    : {e['year']}")
    print(f"     authors : {', '.join(e['authors'][:3])}{'...' if len(e['authors']) > 3 else ''}")

# ── Step 2: S2 citation enrichment ────────────────────────────────────────
print(f"\n{'=' * 80}")
print("STEP 2 — S2 POST /paper/batch  (citation counts + paper IDs)")
print("=" * 80)

s2_ids = [f"ArXiv:{e['arxiv_id']}" for e in entries]
CITE_FIELDS = "paperId,title,year,citationCount,referenceCount,externalIds,authors"

r2 = client.post(
    f"{S2_BASE}/paper/batch",
    params={"fields": CITE_FIELDS},
    json={"ids": s2_ids},
)
print(f"status: {r2.status_code}")
r2.raise_for_status()

cite_data = r2.json()
matched = [item for item in cite_data if item]
not_found = len(cite_data) - len(matched)

print(f"S2 matched: {len(matched)} / {len(s2_ids)}  |  not found: {not_found}\n")
for item in matched:
    ext = item.get("externalIds") or {}
    print(f"  paperId      : {item.get('paperId')}")
    print(f"  arXiv ID     : {ext.get('ArXiv', '(none)')}")
    print(f"  title        : {item.get('title')}")
    print(f"  year         : {item.get('year')}")
    print(f"  citationCount: {item.get('citationCount')}")
    print(f"  refCount     : {item.get('referenceCount')}")
    print()

# ── Step 3: S2 detail (abstract + references) for top-cited paper ─────────
if not matched:
    print("No matched papers — skipping detail step.")
    client.close()
    sys.exit(0)

top = max(matched, key=lambda x: x.get("citationCount") or 0)
print(f"\n{'=' * 80}")
print(f"STEP 3 — S2 POST /paper/batch  (abstract + references)  top-cited paper")
print(f"  paperId: {top['paperId']}  citations: {top.get('citationCount')}")
print("=" * 80)

r3 = client.post(
    f"{S2_BASE}/paper/batch",
    params={"fields": "abstract,references"},
    json={"ids": [top["paperId"]]},
)
print(f"status: {r3.status_code}")
r3.raise_for_status()

detail = r3.json()[0]
abstract = detail.get("abstract")
refs = detail.get("references") or []

print(f"\nabstract ({len(abstract or '')} chars):")
print(f"  {repr(abstract[:200]) if abstract else None}")
print(f"\nreferences: {len(refs)} total  (showing first 3)")
for ref in refs[:3]:
    print(f"  {json.dumps(ref, ensure_ascii=False)}")

client.close()
