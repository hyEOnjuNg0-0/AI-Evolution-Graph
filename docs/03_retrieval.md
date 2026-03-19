## Phase 3 — Retrieval Layer (Layer B)

### 목표

질의에 관련된 Subgraph를 선택하는 검색 파이프라인 구축

### Step 3.1 — Vector Retrieval

**입력**: 사용자 질의 (텍스트)
**출력**: 의미적으로 유사한 논문 리스트 (scored)

* \[x] OpenAI embedding 생성 (text-embedding-3-small)
* \[x] Neo4j Vector Index 구성
* \[x] 논문 embedding 일괄 생성 및 저장
* \[x] Semantic similarity 검색 구현
* \[x] 단위 테스트: embedding 생성, 유사도 계산

### Step 3.2 — Graph Retrieval

**입력**: Seed 논문, hop depth  
**출력**: 구조적으로 연결된 논문 집합

* \[x] Seed 논문 식별 (ID → 논문 매핑)
* \[x] N-hop citation 확장 쿼리 (Cypher, 양방향 CITES)
* \[x] 연결 논문 집합 생성
* \[x] 단위 테스트: hop 확장 정확성, 경계 조건

### Step 3.3 — Hybrid Retrieval

**입력**: 질의, 검색 파라미터 (α, β, 질의 유형)
**출력**: Query-specific Subgraph

#### 점수 정의

```
hybrid_score = α × semantic_similarity + β × graph_proximity
```

**semantic_similarity**
- 벡터 검색(cosine similarity)으로 산출, 범위 [0, 1]
- 벡터 검색 결과에 없는 논문(그래프 확장으로만 발견된 것)은 0으로 고정

**graph_proximity** — 역수 감쇠 방식
- `graph_proximity = 1.0 / hop_distance`
- 시드 논문(hop = 0): `1.0`, hop 1: `1.0`, hop 2: `0.5`, hop 3: `0.33`, ...
- 그래프 이웃에 없는 논문: `0.0`

#### 파이프라인 흐름

```
query + params (α, β, query_type, top_k, hops)
    ↓
[1] VectorRetrievalService.search(query, top_k)     → 의미 유사 후보 (시드)
    ↓ 상위 top_k 개를 seed로 사용
[2] GraphRepositoryPort (hop 거리 포함 확장)         → 구조적 이웃 후보
    ↓
[3] 후보 합집합 구성
    ├─ 벡터 후보: semantic_sim=cosine, graph_prox=1.0 (시드이므로)
    └─ 그래프 확장 후보: semantic_sim=0.0, graph_prox=1/hop_dist
    ↓
[4] hybrid_score = α × semantic_sim + β × graph_prox
    ↓
[5] Top-k 선택 → Subgraph 구성
```

#### 질의 유형별 가중치

| query_type | α | β |
|---|---|---|
| `"semantic"` | 0.9 | 0.1 |
| `"structural"` | 0.1 | 0.9 |
| `"balanced"` | 0.5 | 0.5 |

#### 구현 사항

* \[x] `GraphRepositoryPort`에 `get_citation_neighborhood_with_distances(paper_id, hops) → list[tuple[Paper, int]]` 추가
* \[x] `Neo4jGraphRepository` Cypher 수정 (hop 거리 반환)
* \[x] `HybridRetrievalService` 구현 (위 파이프라인)
* \[x] 질의 유형별 가중치 자동 조정 로직
* \[x] Subgraph 출력 포맷 정의 (`Subgraph(papers: list[ScoredPaper])` in models.py)
* \[x] 단위 테스트: 점수 계산, 가중치 조정
* \[ ] 통합 테스트: Layer A 그래프 → Retrieval 파이프라인

### Phase 3 산출물

* **Query-specific Subgraph** 생성 기능
* Vector / Graph / Hybrid 3가지 검색 전략

### 검증 기준 (RQ1 연계)

* Human relevance score
* Citation coverage
* Grounding score

