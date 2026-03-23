"""Semantic Scholar raw 데이터 확인용 스크립트.

SemanticScholarClient와 동일한 fields 파라미터로 실제 API 응답을 확인.

사용법:
  python check_data.py                    # 기본: NeurIPS 2023, top 1
  python check_data.py ICML 2024          # 다른 학회/연도
  python check_data.py CVPR 2023 3        # 건수 지정
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import json
import httpx

VENUE = sys.argv[1] if len(sys.argv) > 1 else "NeurIPS"
YEAR = sys.argv[2] if len(sys.argv) > 2 else "2023"
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 1

BASE = "https://api.semanticscholar.org/graph/v1"

# Bulk search does not support 'abstract' or 'references' fields
BULK_FIELDS = "title,year,venue,citationCount,referenceCount,authors"
# Batch endpoint fields to verify support for abstract and references
BATCH_FIELDS = "abstract,references"

client = httpx.Client(timeout=30)

# 1) Bulk search — get paper IDs
r = client.get(
    f"{BASE}/paper/search/bulk",
    params={"venue": VENUE, "year": YEAR, "fields": BULK_FIELDS},
)
r.raise_for_status()
data = r.json()

print(f"total: {data.get('total', 0)}  |  this page: {len(data.get('data', []))}\n")

top = sorted(data.get("data", []), key=lambda x: x.get("citationCount", 0), reverse=True)[:LIMIT]
paper_ids = [p["paperId"] for p in top]

for i, paper in enumerate(top, 1):
    print("=" * 80)
    print(f"[{i}/{LIMIT}] BULK SEARCH RESPONSE")
    print("=" * 80)
    print(json.dumps(paper, indent=2, ensure_ascii=False))

# 2) POST /paper/batch — verify abstract and references fields
print(f"\n{'=' * 80}")
print(f"POST /paper/batch  fields={BATCH_FIELDS}  ids={paper_ids}")
print("=" * 80)

r2 = client.post(
    f"{BASE}/paper/batch",
    params={"fields": BATCH_FIELDS},
    json={"ids": paper_ids},
)
print(f"status: {r2.status_code}")
if r2.status_code == 200:
    batch_data = r2.json()
    for item in batch_data:
        pid = item.get("paperId", "?")
        abstract = item.get("abstract")
        refs = item.get("references", [])
        print(f"\npaperId : {pid}")
        print(f"abstract: {repr(abstract) if abstract else None}")
        print(f"references ({len(refs)} items, showing first 3):")
        for ref in refs[:3]:
            print(f"  {json.dumps(ref, ensure_ascii=False)}")
else:
    print(json.dumps(r2.json(), indent=2, ensure_ascii=False))

client.close()
