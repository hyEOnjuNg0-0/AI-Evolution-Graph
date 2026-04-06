# Trend Momentum Analysis 기능 분리 계획

> 작성일: 2026-04-06  
> 대상 브랜치: main  
> 관련 파일: `src/aievograph/api/routers/trend.py`, `src/aievograph/domain/services/`

---

## 배경

현재 `POST /api/trend`는 서로 다른 두 가지 사용 의도를 하나의 엔드포인트에 묶고 있다.

| 의도 | 설명 |
|---|---|
| **탐색(Search)** | 내가 아는 method가 어떻게 진화했는지 추적 |
| **발견(Discovery)** | 특정 기간에 어떤 method가 주목받았는지 탐색 |

이 둘은 입력 구조, UX 패턴, 핵심 알고리즘이 모두 다르므로 분리가 적합하다.

---

## 현재 구조의 문제

```
POST /api/trend
  입력: topic(검색어) + start_year + end_year
  처리:
    1. 전체 method 이름 조회 (19,639개)
    2. topic으로 case-insensitive substring 필터링
    3. 필터된 subset에 대해 CAGR / Entropy / Velocity 계산
    4. EvolutionPathService로 진화 경로 추출
  출력: 단일 method의 점수 + evolution_path
```

- `topic`이 없으면 동작 불가 → Discovery 용도로 쓸 수 없음
- 점수 계산(Trend)과 경로 추출(Evolution)이 불필요하게 결합되어 있음

---

## 분리 설계

### Feature A — Method Evolution Path

> "검색한 method의 진화 경로를 확인한다"

**엔드포인트**: `POST /api/evolution` (신규)

| 항목 | 내용 |
|---|---|
| 입력 | `method_name` (필수), `start_year`, `end_year` |
| 출력 | evolution DAG (from→to, relation_type), yearly adoption counts, influence scores |
| 핵심 서비스 | `EvolutionPathService.extract()` (기존, 재사용) |
| 변경 범위 | `routers/evolution.py` 신규, `schemas/evolution.py` 신규 |

**Request 예시**:
```json
{
  "method_name": "Transformer",
  "start_year": 2017,
  "end_year": 2024
}
```

**Response 예시**:
```json
{
  "method_name": "Transformer",
  "evolution_path": [
    {"from_method": "RNN", "to_method": "Transformer", "relation_type": "REPLACES"},
    {"from_method": "Transformer", "to_method": "Vision Transformer", "relation_type": "EXTENDS"}
  ],
  "yearly_counts": {"2017": 12, "2018": 89, "2019": 340},
  "influence_scores": {"Transformer": 0.92, "Vision Transformer": 0.68}
}
```

---

### Feature B — Trending Methods Discovery

> "지정한 기간에 주목받은 method를 발견한다"

**엔드포인트**: `POST /api/trend` (기존 엔드포인트 재활용, 스키마 변경)

| 항목 | 내용 |
|---|---|
| 입력 | `start_year`, `end_year`, `top_k` (선택, 기본값 30) |
| 출력 | 기간 내 TOP-K ranked methods (momentum score 순위) |
| 핵심 서비스 | `TrendMomentumService.score()` (기존, 재사용) |
| 변경 범위 | `TrendRequest`에서 `topic` 제거, Repository에 전체 조회 메서드 추가 |

**Request 예시**:
```json
{
  "start_year": 2020,
  "end_year": 2024,
  "top_k": 20
}
```

**Response 예시**:
```json
{
  "start_year": 2020,
  "end_year": 2024,
  "methods": [
    {
      "method_name": "LoRA",
      "cagr": 0.91,
      "entropy": 0.78,
      "adoption_velocity": 0.85,
      "momentum_score": 0.85,
      "yearly_counts": {"2020": 3, "2021": 18, "2022": 97, "2023": 412, "2024": 890}
    },
    ...
  ]
}
```

---

## 기술 구현 상세

### 백엔드 변경 사항

#### 1. `MethodTrendRepositoryPort` — 신규 메서드 추가

Discovery 모드에서는 19,639개 이름을 파라미터로 넘기지 않고, `IN` 필터 없이 전체를 조회하는 전용 쿼리를 사용한다.

```python
# ports/method_trend_repository.py 에 추가
@abstractmethod
def get_all_yearly_usage_counts(
    self,
    year_start: int,
    year_end: int,
) -> dict[str, dict[int, int]]: ...

@abstractmethod
def get_all_venue_distributions(
    self,
    year_start: int,
    year_end: int,
) -> dict[str, dict[str, int]]: ...
```

#### 2. `Neo4jMethodTrendRepository` — 전체 조회 쿼리 추가

```cypher
-- 기존: WHERE m.name IN $method_names
-- 신규 (Discovery): 필터 없이 전체 조회
MATCH (p:Paper)-[:USES]->(m:Method)
WHERE p.publication_year >= $year_start
  AND p.publication_year <= $year_end
RETURN m.name AS method_name, p.publication_year AS year, count(p) AS cnt
```

#### 3. `TrendMomentumService` — Discovery 모드 오버로드 or 파라미터 분기

- `method_names=None` 이면 전체 조회 메서드 사용
- TOP-K 반환 개수 파라미터 추가

#### 4. `routers/trend.py` — `topic` 파라미터 제거, Response 스키마 변경

#### 5. `routers/evolution.py` — 신규 파일 생성

---

### 프론트엔드 변경 사항

| 파일 | 변경 내용 |
|---|---|
| `components/trend-view.tsx` | 검색창 제거, year range + TOP-K 결과 테이블/차트로 교체 |
| `components/evolution-view.tsx` | 신규: method 검색 입력 + DAG 시각화 (`graph-view-panel` 재사용) |
| `lib/api.ts` | `TrendRequest`/`TrendResponse` 타입 수정, `EvolutionRequest`/`EvolutionResponse` 추가 |

---

## 파일 변경 목록 요약

### 신규 생성
- `src/aievograph/api/routers/evolution.py`
- `src/aievograph/api/schemas/evolution.py`
- `frontend/components/evolution-view.tsx`

### 수정
- `src/aievograph/domain/ports/method_trend_repository.py` — 전체 조회 추상 메서드 추가
- `src/aievograph/infrastructure/neo4j_method_trend_repository.py` — 전체 조회 구현 추가
- `src/aievograph/domain/services/trend_momentum_service.py` — Discovery 모드 분기 추가
- `src/aievograph/api/routers/trend.py` — `topic` 제거, evolution 로직 분리
- `src/aievograph/api/schemas/trend.py` — Request/Response 스키마 변경
- `src/aievograph/api/main.py` — evolution 라우터 등록
- `frontend/components/trend-view.tsx` — UI 재설계
- `frontend/lib/api.ts` — 타입 수정

---

## Breaking Change 주의

`POST /api/trend` 스키마가 변경된다:
- `topic` 필드 **제거** (기존 클라이언트 호환 불가)
- `top_k` 필드 **추가**
- Response 구조 **변경** (단일 method → method 배열)

프론트엔드와 동시에 변경해야 한다.
