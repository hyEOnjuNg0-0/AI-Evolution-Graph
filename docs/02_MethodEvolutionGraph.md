# Phase 2 — Knowledge Graph Construction Layer — Method Evolution Graph (Layer A-2)

## 목표

논문 Abstract에서 방법론(Method) 엔티티와 방법론 간 진화 관계를 추출하여 그래프로 구축

> **선행 조건**: `01_TemporalCitationGraph.md`의 논문 수집(Step 1)이 완료되어 Paper 노드가 Neo4j에 존재해야 한다.

## 전체 흐름

```
Paper Abstract → LLM 엔티티+관계 동시 추출 (GraphRAG 스타일) → Entity Normalization → Neo4j 저장 → Method Evolution Graph
```

## 추출 전략

GraphRAG(Microsoft)의 프롬프트 설계 패턴을 차용하되, 패키지 자체는 사용하지 않는다.

- **GraphRAG 패키지 미사용**: OpenAI SDK로 GPT-4o 직접 호출 (의존성 최소화)
- **GraphRAG 프롬프트 패턴 차용**:
  - 엔티티 + 관계 동시 추출 (single-pass extraction)
  - 구조화된 출력 포맷 (엔티티명, 타입, 설명 / 관계 소스, 타겟, 유형, 근거)
  - Gleaning (반복 추출로 누락 방지)
- **도메인 특화 커스터마이징**:
  - 엔티티 타입: `Method`, `Model`, `Technique`, `Framework`
  - 관계 유형: `IMPROVES`, `EXTENDS`, `REPLACES` (논문 간 citation과는 별개)

---

## Step 2.1 — Method Entity & Relationship Extraction

**입력**: 논문 Abstract  
**출력**: (Method 엔티티 리스트, Method 간 관계 리스트)

- [x] 추출 프롬프트 설계 (GraphRAG 스타일)
  - 엔티티: 이름, 타입(Method/Model/Technique/Framework), 설명
  - 관계: 소스 Method, 타겟 Method, 유형(IMPROVES/EXTENDS/REPLACES), 근거 텍스트
  - few-shot 예시 구성 (AI 논문 도메인)
- [x] Structured output 스키마 정의 (Pydantic 모델)
- [x] Gleaning 구현 (1차 추출 후 누락 여부 재확인)
- [x] 배치 처리 (다수 Abstract 일괄 추출)
- [x] 단위 테스트: 추출 정확도, 출력 스키마 검증

---

## Step 2.2 — Entity Normalization

**입력**: 추출된 Method 엔티티 리스트  
**출력**: 정규화된 Method 엔티티 리스트

- [x] 유사 엔티티 통합 (예: "BERT", "bert-base", "BERT-large" → "BERT")
  - 문자열 유사도 + LLM 기반 판단 병행
- [x] 정규화 매핑 테이블 관리
- [x 단위 테스트: normalization 로직

> **참고**: GraphRAG의 커뮤니티 탐지와는 다른 단계이다.
> - Normalization = 동일 엔티티 병합 (노드 수 감소)
> - Community Detection = 관련 엔티티 군집화 (상위 클러스터 생성)
> 
> 커뮤니티 탐지는 Normalization 이후 선택적으로 적용하여 방법론 패러다임 클러스터(예: "Transformer 계열", "GAN 계열")를 생성할 수 있다. → Layer D(Analytical) 분석에 활용 가능

---

## Step 2.3 — Neo4j 저장

**입력**: 정규화된 Method 엔티티 + 관계  
**출력**: Method Evolution Graph (Neo4j)

- [ ] Method 노드 생성 (속성: name, type, description)
- [ ] Method 간 관계 edge 생성 (속성: relation_type, evidence)
- [ ] Paper-Method 연결: `(:Paper)-[:USES]->(:Method)`
- [ ] Neo4j 스키마: `(:Method)-[:IMPROVES|EXTENDS|REPLACES]->(:Method)`
- [ ] 통합 테스트: Abstract → Method Graph 파이프라인

---

## phase 2 산출물

- **Method Evolution Graph** (Neo4j)
  - Method 노드 + 진화 관계 (IMPROVES / EXTENDS / REPLACES)
  - Paper-Method 연결 (USES)

## 검증 기준

- Method entity 품질 샘플링 검토
- Normalization 정확도 (중복 엔티티 비율)
- Relation extraction 정확도 (샘플 기반 검증)
- Gleaning 적용 전후 재현율(recall) 비교
