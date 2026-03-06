"""Semantic Scholar raw 데이터 확인용 스크립트.

논문 메타데이터 + references/citations 인용 관계까지 확인.

사용법:
  python check_data.py                    # 기본: NeurIPS 2023, top 1
  python check_data.py ICML 2024          # 다른 학회/연도
  python check_data.py CVPR 2023 3        # 건수 지정
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import json
import time
import httpx

VENUE = sys.argv[1] if len(sys.argv) > 1 else "NeurIPS"
YEAR = sys.argv[2] if len(sys.argv) > 2 else "2023"
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 1

BASE = "https://api.semanticscholar.org/graph/v1"

client = httpx.Client(timeout=30)

# 1) Bulk search (no fields param = all default fields)
r = client.get(f"{BASE}/paper/search/bulk", params={"venue": VENUE, "year": YEAR})
r.raise_for_status()
data = r.json()

print(f"total: {data.get('total', 0)}  |  this page: {len(data.get('data', []))}\n")

top = sorted(data.get("data", []), key=lambda x: x.get("citationCount", 0), reverse=True)[:LIMIT]

for i, paper in enumerate(top, 1):
    pid = paper["paperId"]
    title = paper["title"]

    # 2) 논문 메타데이터
    print("=" * 80)
    print(f"[{i}/{len(top)}] PAPER")
    print("=" * 80)
    print(json.dumps(paper, indent=2, ensure_ascii=False))

    # 3) References raw
    time.sleep(1)
    r = client.get(f"{BASE}/paper/{pid}/references", params={"limit": 5})
    print(f"\n{'=' * 80}")
    print(f"REFERENCES raw (limit=5)")
    print("=" * 80)
    print(json.dumps(r.json() if r.status_code == 200 else {"error": r.status_code}, indent=2, ensure_ascii=False))

    # 4) Citations raw
    time.sleep(1)
    r = client.get(f"{BASE}/paper/{pid}/citations", params={"limit": 5})
    print(f"\n{'=' * 80}")
    print(f"CITATIONS raw (limit=5)")
    print("=" * 80)
    print(json.dumps(r.json() if r.status_code == 200 else {"error": r.status_code}, indent=2, ensure_ascii=False))

    print("\n")

client.close()
