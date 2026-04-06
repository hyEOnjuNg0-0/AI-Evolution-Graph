## Phase 6 — Interface Layer (Layer E)

### 목표
분석 결과를 직관적으로 탐색할 수 있는 웹 인터페이스 구축

### Step 6.1 — 프로젝트 설정 및 API 연동

- [x] Next.js + TailwindCSS + ShadCN 프로젝트 초기화
- [x] Python 백엔드 API 설계 (FastAPI)
- [x] API 엔드포인트 정의 (lineage / breakthrough / trend)
- [x] 프론트엔드-백엔드 통신 구조 확립 (TypeScript API client)

### Step 6.2 — Query Panel

**기능 ①: Research Lineage Exploration**

- [x] Seed paper / keyword 입력
- [x] Hop depth, Time range (start_year / end_year) 슬라이더
- [x] query_type 선택 (semantic / structural / balanced)
- [x] 검색 실행 및 결과 테이블 수신 (score, citation_count 포함)

### Step 6.3 — Graph View Panel

**Citation Graph (Lineage 결과 시각화)**

- [x] SVG 기반 force-directed 그래프 렌더링 (Fruchterman-Reingold, 외부 라이브러리 없음)
- [x] 노드: year 레이블, hybrid score로 색상 변화 (진한 파랑 = 높은 score)
- [x] 엣지: citation 방향 화살표 (SVG marker)
- [x] 노드 클릭 → 상세 패널 (title, authors, year, citation_count, score, Semantic Scholar 링크)
- [x] year 슬라이더로 그래프 시간 필터링 (Query Panel 쿼리 결과 기준 범위 자동 조정)

**Evolution Path (Trend 결과 시각화)**

- [x] evolution_path 스텝을 수평 DAG로 렌더링 (from_method → to_method, relation_type 레이블 표시)
- [x] 각 노드에 breakthrough 여부 배지 표시 (composite_score ≥ 0.5 임계값 기준, ★ 아이콘)

### Step 6.4 — Insight Panel

**기능 ②: Breakthrough Detection**

- [x] field, start_year / end_year, top_k 입력
- [x] 결과 테이블: title, year, burst_score, centrality_shift, composite_score
- [x] composite_score 기준 bar 차트 (top-k 시각화)
- [x] 선택한 후보를 Graph View에 하이라이트 (노드 색상 변경, amber 테두리)

**기능 ③: Trend Momentum Analysis**

- [x] topic, start_year / end_year 입력
- [x] 스코어 분해 카드: CAGR / Entropy / Adoption Velocity / 종합 momentum_score
- [x] evolution_path → 6.3 Graph View로 전달 (공유 상태)

### Step 6.5 — 통합 레이아웃 및 Evidence Panel

- [x] 3-패널 레이아웃: Query/Insight (좌) | Graph View (중) | Evidence (우)
- [x] Evidence Panel: 선택 논문의 score 근거 표시
  - hybrid_score 분해 (semantic_similarity vs graph_proximity)
  - Semantic Scholar 원문 링크 (`semanticscholar.org/paper/{paper_id}`)
- [x] 전역 상태 관리 (선택 논문 공유, 패널 간 연동)

### Phase 6 산출물
- 완성된 웹 인터페이스

### 검증 기준
- 3가지 주요 기능 시나리오 E2E 테스트
- 사용성 검토
