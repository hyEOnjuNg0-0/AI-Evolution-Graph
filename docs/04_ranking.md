## Phase 4 — Subgraph Refinement \& Ranking Layer (Layer C)

### 목표

Subgraph에서 핵심 축을 추출하고 순위를 매기는 파이프라인 구축

### Step 4.1 — Centrality-based Ranking

**입력**: Subgraph  
**출력**: 구조적 중요도 점수가 부여된 논문 리스트

* \[X] Neo4j GDS를 활용한 PageRank 계산
* \[X] Betweenness Centrality 계산
* \[X] Subgraph 범위 내 centrality 계산 로직
* \[X] 단위 테스트: centrality 계산 정확성

### Step 4.2 — Embedding Similarity Ranking

**입력**: 질의 embedding, Subgraph 내 논문 embeddings  
**출력**: 의미적 중요도 점수가 부여된 논문 리스트

* \[ ] 질의-논문 embedding 유사도 계산
* \[ ] 점수 정규화
* \[ ] 단위 테스트: 유사도 계산, 정규화

### Step 4.3 — Hybrid Ranking \& Graph Pruning

**입력**: Centrality 점수, Semantic 점수, Subgraph
**출력**: Top-k ranked papers + 핵심 경로

* \[ ] Centrality + Semantic score 결합 로직
* \[ ] Graph pruning (backbone extraction) 알고리즘 구현

  * 계보를 가장 잘 설명하는 핵심 경로만 추출
* \[ ] Top-k 논문 리스트 생성
* \[ ] 설명 가능한 구조 경로 생성
* \[ ] 단위 테스트: 결합 점수, pruning 결과
* \[ ] 통합 테스트: Subgraph → Ranking 파이프라인

### Phase 4 산출물

* **Top-k ranked papers** 리스트
* **구조 경로** (설명 가능한 계보 경로)

### 검증 기준 (RQ2, RQ3 연계)

* Precision@k, Hallucination rate, Graph density (RQ2)
* Known milestone recall, Betweenness correlation (RQ3)

