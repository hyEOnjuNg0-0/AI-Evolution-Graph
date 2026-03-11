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

# Bulk search does not support 'references' field
BULK_FIELDS = "title,year,venue,citationCount,referenceCount,authors"

client = httpx.Client(timeout=30)

# 1) Bulk search
r = client.get(
    f"{BASE}/paper/search/bulk",
    params={"venue": VENUE, "year": YEAR, "fields": BULK_FIELDS},
)
r.raise_for_status()
data = r.json()

print(f"total: {data.get('total', 0)}  |  this page: {len(data.get('data', []))}\n")

top = sorted(data.get("data", []), key=lambda x: x.get("citationCount", 0), reverse=True)[:LIMIT]

for i, paper in enumerate(top, 1):
    pid = paper["paperId"]

    print("=" * 80)
    print(f"[{i}/{LIMIT}] BULK SEARCH RESPONSE")
    print("=" * 80)
    print(json.dumps(paper, indent=2, ensure_ascii=False))

    # 2) /paper/{id}/references — check actual response structure
    import time; time.sleep(1)
    r2 = client.get(f"{BASE}/paper/{pid}/references", params={"limit": 3})
    print(f"\n{'=' * 80}")
    print(f"REFERENCES ENDPOINT (limit=3)")
    print("=" * 80)
    print(json.dumps(r2.json() if r2.status_code == 200 else {"error": r2.status_code}, indent=2, ensure_ascii=False))
    print()

client.close()
