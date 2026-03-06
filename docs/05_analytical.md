## Phase 5 — Analytical Layer (Layer D)

### 목표
구조적 변화, 확산 속도, 진화 경로를 정량화하는 분석 엔진 구축

### Step 5.1 — Breakthrough Detection

**입력**: Temporal Citation Graph, 시간 윈도우
**출력**: Breakthrough 후보 리스트

- [ ] Kleinberg burst detection 알고리즘 구현 (Citation burst)
- [ ] 시간 윈도우 간 centrality 변화 측정 (Centrality shift)
- [ ] Breakthrough 후보 점수화 및 순위
- [ ] 단위 테스트: burst detection, centrality shift 계산

### Step 5.2 — Trend Momentum Score

**입력**: Method Evolution Graph, 최근 n년 파라미터  
**출력**: Trend score (method별)

- [ ] Recent citation CAGR 계산
- [ ] Diversity entropy 계산 (Shannon entropy)
- [ ] Adoption velocity 계산 (diffusion speed)
- [ ] Trend score = α × CAGR + β × Entropy + γ × AdoptionVelocity
- [ ] 단위 테스트: 각 지표 계산, 종합 점수

### Step 5.3 — Evolution Path 생성

**입력**: Method Evolution Graph, Breakthrough 후보, Trend Score
**출력**: Evolution path (핵심 경로, 분기 지점, 영향력 점수)

- [ ] 핵심 경로 추출 알고리즘
- [ ] 분기 지점 식별
- [ ] 영향력 점수 통합
- [ ] 통합 테스트: Layer A 그래프 → 분석 파이프라인 전체

### Phase 5 산출물
- **Breakthrough 후보** 리스트
- **Trend score** (method별)
- **Evolution path**

### 검증 기준
- 알려진 breakthrough (Transformer, ResNet 등)와의 일치도
- Trend score와 실제 연구 동향 비교