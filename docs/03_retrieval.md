## Phase 3 — Retrieval Layer (Layer B)

### 목표
질의에 관련된 Subgraph를 선택하는 검색 파이프라인 구축

### Step 3.1 — Vector Retrieval

**입력**: 사용자 질의 (텍스트)
**출력**: 의미적으로 유사한 논문 리스트 (scored)

- [ ] OpenAI embedding 생성 (text-embedding-3-small)
- [ ] Neo4j Vector Index 구성
- [ ] 논문 embedding 일괄 생성 및 저장
- [ ] Semantic similarity 검색 구현
- [ ] 단위 테스트: embedding 생성, 유사도 계산

### Step 3.2 — Graph Retrieval

**입력**: Seed 논문, hop depth  
**출력**: 구조적으로 연결된 논문 집합

- [ ] Seed 논문 식별 (ID 또는 keyword → 논문 매핑)
- [ ] N-hop citation 확장 쿼리 (Cypher)
- [ ] 연결 논문 집합 생성
- [ ] 단위 테스트: hop 확장 정확성, 경계 조건

### Step 3.3 — Hybrid Retrieval

**입력**: 질의, 검색 파라미터 (α, β, 질의 유형)  
**출력**: Query-specific Subgraph

- [ ] score = α × semantic_similarity + β × graph_proximity 구현
- [ ] 질의 유형별 가중치 자동 조정 로직
- [ ] Top-k 선택 및 Subgraph 구성
- [ ] Subgraph 출력 포맷 정의 (논문 노드, citation edge, method/author 노드)
- [ ] 단위 테스트: 점수 계산, 가중치 조정
- [ ] 통합 테스트: Layer A 그래프 → Retrieval 파이프라인

### Phase 3 산출물
- **Query-specific Subgraph** 생성 기능
- Vector / Graph / Hybrid 3가지 검색 전략

### 검증 기준 (RQ1 연계)
- Human relevance score
- Citation coverage
- Grounding score