# Phase 1 — Knowledge Graph Construction Layer — Temporal Citation Graph (Layer A-1)

## 목표

논문 수집 → Citation edge 생성 → 시간 속성이 포함된 인용 그래프 구축

## 전체 흐름

```
Semantic Scholar Bulk API → Paper 수집/필터링 → Paper 노드 생성 → Citation Edge 생성 → Temporal Citation Graph (Neo4j)
```

---

## Step 1.1 — 논문 수집 (Semantic Scholar)

**입력**: 학회 목록, 연도 범위, 인용 수 threshold  
**출력**: 정규화된 Paper 도메인 객체 리스트

> OpenAlex는 NeurIPS, ICML, ICLR 등 주요 ML 학회의 venue 매핑이 2022년 이후 누락되어
> Semantic Scholar Bulk API로 전환. 모든 학회에서 venue 필터가 정상 동작 확인됨.

- [x] Semantic Scholar Bulk API 클라이언트 구현
- [x] 학회 필터 (venue 파라미터)
    - ML 일반: NeurIPS, ICML, ICLR
    - NLP: ACL, EMNLP, NAACL
    - CV: CVPR, ICCV, ECCV
    - AI 일반: AAAI, IJCAI
    - Data/IR: KDD, SIGIR
    - 기타: ICRA (Robotics), AISTATS
- [x] 연도 범위 필터 (최근 15년)
- [x] 연도별 top 20% 인용 수 threshold 적용
- [x] Paper 도메인 모델로 변환
- [x] 수집 결과 로컬 캐싱 (재수집 방지)
- [x] 단위 테스트: 필터링 로직, 모델 변환

---

## Step 1.2 — Citation Edge 생성

**입력**: Paper 리스트  
**출력**: Temporal Citation Graph (Neo4j)

- [ ] Neo4j 어댑터 구현 (Repository 패턴)
- [ ] Paper 노드 생성
- [ ] Citation edge 생성 (참조 관계)
- [ ] Neo4j 노드/관계 스키마: `(:Paper)-[:CITES]->(:Paper)`, `(:Paper)-[:WRITTEN_BY]->(:Author)`
  - Author는 Semantic Scholar author ID 사용
- [ ] Timestamp 속성 (publication_year) 인덱싱
- [ ] 시간 범위 필터링 쿼리 구현
- [ ] 단위 테스트: 그래프 CRUD, 시간 필터
- [ ] 통합 테스트: Semantic Scholar → Neo4j 파이프라인

---

## Phase 1 산출물

- **Temporal Citation Graph** (Neo4j)
  - Paper 노드 + CITES 관계 + Author 노드
  - 시간 범위 필터링 가능

## 검증 기준

- 수집 논문 수 및 venue coverage 확인
- 연도 분포 정상 여부
- citation edge 시간 일관성 통과율
- reference 매칭 성공률
- 시간 필터링 쿼리 정확성
