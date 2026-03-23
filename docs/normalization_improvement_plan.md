# Method Normalization 개선 계획

> 작성일: 2026-03-23
> 상태: 계획 확정, 미착수

## 배경 및 문제 정의

현재 Method Graph 수집 파이프라인의 정규화(normalization)는 **배치 내부(intra-batch)로 범위가 제한**되어 있다.

`MethodGraphService.build_method_graph(papers)`의 실행 흐름:

```
[새 논문 배치]
    → extract_from_papers()   # 새 논문에서만 추출
    → normalize(raw_results)  # 새 논문끼리만 정규화
    → upsert_method()         # Neo4j에 저장 (name 기반 MERGE)
```

`EntityNormalizationService.normalize()`는 전달받은 results 목록 안에서만 Method 이름을 수집하고 `NormalizationMap`을 생성한다. Neo4j에 이미 존재하는 Method 노드는 조회하지 않는다.

### 결과적으로 발생하는 문제

| 시나리오 | 결과 |
|---|---|
| 1차 ingest: "BERT", "Bert" → 정규화 → "BERT" 저장 | 정상 |
| 2차 ingest: "bert" 등장 → 배치 내 다른 이름 없으면 정규화 skip | "bert" 노드 신규 생성 |
| Neo4j 상태 | "BERT"와 "bert" 두 노드 공존 (중복) |

`--method-graph-only` 옵션으로 연도 범위를 달리해 여러 번 실행하거나, arXiv와 Semantic Scholar에서 별도 수집할 경우 중복이 누적된다.

---

## 개선 전략

```
Phase 1: 중복 허용 → 사후 제거 (dedup job)
Phase 2: 점진적 예방 (Persistent NormalizationMap)
```

---

## Phase 1 — 사후 중복 제거 job

**목표**: DB에 이미 쌓인 중복 Method 노드를 병합하는 `scripts/dedup_methods.py` 구현

### Step 1-1. Port에 2개 추상 메서드 추가

**파일**: `src/aievograph/domain/ports/graph_repository.py`

| 메서드 | 시그니처 | 역할 |
|---|---|---|
| `get_all_method_names` | `() -> list[str]` | Neo4j의 모든 Method 노드 이름 반환 |
| `merge_method_nodes` | `(canonical_name: str, variant_name: str) -> None` | variant 노드를 canonical로 병합 후 삭제 |

기존 코드 변경 없음 — Port에 추상 메서드 추가만.

### Step 1-2. Neo4jGraphRepository에 구현 추가

**파일**: `src/aievograph/infrastructure/neo4j_graph_repository.py`

**`get_all_method_names` Cypher**:
```cypher
MATCH (m:Method) RETURN m.name ORDER BY m.name
```

**`merge_method_nodes` 실행 순서** (단일 세션, 8단계):

```
1. USES 재연결:       (:Paper)-[:USES]->(variant)  →  (:Paper)-[:USES]->(canonical)
2. incoming IMPROVES: (:src)-[:IMPROVES]->(variant) →  (:src)-[:IMPROVES]->(canonical)
3. incoming EXTENDS:  (:src)-[:EXTENDS]->(variant)  →  (:src)-[:EXTENDS]->(canonical)
4. incoming REPLACES: (:src)-[:REPLACES]->(variant) →  (:src)-[:REPLACES]->(canonical)
5. outgoing IMPROVES: (variant)-[:IMPROVES]->(tgt)  →  (canonical)-[:IMPROVES]->(tgt)
6. outgoing EXTENDS:  (variant)-[:EXTENDS]->(tgt)   →  (canonical)-[:EXTENDS]->(tgt)
7. outgoing REPLACES: (variant)-[:REPLACES]->(tgt)  →  (canonical)-[:REPLACES]->(tgt)
8. variant 노드 삭제: DETACH DELETE variant
```

Self-loop 방지 조건: outgoing 단계에서 `WHERE tgt.name <> $variant AND tgt.name <> $canonical` 추가.

**완료 조건**: `merge_method_nodes("BERT", "bert")` 호출 후 Neo4j에 `bert` 노드가 존재하지 않고, `bert`의 모든 엣지가 `BERT`로 이전되어 있을 것.

### Step 1-3. MethodDeduplicationService 신규 생성

**파일**: `src/aievograph/domain/services/method_deduplication_service.py`

```
MethodDeduplicationService
  __init__(repo: GraphRepositoryPort, normalizer: EntityNormalizerPort)
  deduplicate() -> NormalizationMap
```

**`deduplicate()` 실행 흐름**:
```
1. repo.get_all_method_names() → list[str]
2. list[str] → list[Method] 변환 후 normalizer.normalize(methods) 호출
3. NormalizationMap.mapping 순회:
     for variant, canonical in norm_map.mapping.items():
         repo.merge_method_nodes(canonical, variant)
4. return norm_map
```

**완료 조건**: `deduplicate()` 실행 후 반환된 `NormalizationMap.mapping`의 모든 variant가 Neo4j에 존재하지 않을 것.

### Step 1-4. scripts/dedup_methods.py 신규 생성

```
--dry-run  : merge 없이 NormalizationMap만 출력 (실제 변경 없음)
--llm-model: normalizer에 사용할 모델 (기본: gpt-4o-mini, 비용 절감)
```

**dry-run 필수**: 실제 DB 변경 전 어떤 노드가 병합될지 사전 확인 가능해야 함.

### Phase 1 테스트 계획

| 테스트 파일 | 대상 | 핵심 시나리오 |
|---|---|---|
| `tests/test_method_deduplication_service.py` | `MethodDeduplicationService` | stub repo에서 `["BERT", "bert"]` 반환 시 `merge_method_nodes("BERT", "bert")` 1회 호출됨을 검증 |
| `tests/test_neo4j_graph_repository.py` (추가) | `merge_method_nodes` | 통합 테스트: variant의 USES/관계 엣지가 canonical로 이전되고 variant 삭제됨 |

---

## Phase 2 — Persistent NormalizationMap (점진적 예방)

> **이 변경은 리팩토링을 포함합니다. 진행 전 승인이 필요합니다.**
> `MethodGraphService.build_method_graph()` — 현재 동작 중인 코드를 수정합니다.

**목표**: 새 ingest 실행 시 이전 run의 canonical 이름을 참조하여 배치 간 중복을 예방

### Step 2-1. NormalizationMapStore Port 신규 생성

**파일**: `src/aievograph/domain/ports/normalization_map_store.py`

```python
class NormalizationMapStorePort(ABC):
    def load(self) -> NormalizationMap: ...   # 없으면 NormalizationMap() 반환
    def save(self, norm_map: NormalizationMap) -> None: ...
```

### Step 2-2. FileNormalizationMapStore 구현

**파일**: `src/aievograph/infrastructure/file_normalization_map_store.py`

- JSON 파일 (`data/normalization_map.json`)에 `NormalizationMap.mapping` 직렬화/역직렬화
- 기존 `file_cache.py` 패턴 재사용

### Step 2-3. EntityNormalizationService.normalize() 시그니처 확장

**현재**:
```python
normalize(results: list[tuple[str, ExtractionResult]]) -> tuple[..., NormalizationMap]
```

**변경**:
```python
normalize(
    results: list[tuple[str, ExtractionResult]],
    existing_map: NormalizationMap | None = None,  # 추가 (optional)
) -> tuple[..., NormalizationMap]
```

기존 호출부는 `existing_map` 없이 호출 → 하위 호환 유지.

**내부 동작 변경**: `existing_map`이 있으면 새 이름들을 기존 canonical에 먼저 매핑 시도 후, 미매핑 이름만 LLM 클러스터링으로 전달.

### Step 2-4. MethodGraphService.build_method_graph() 수정

```python
def build_method_graph(
    self,
    papers: list[Paper],
    map_store: NormalizationMapStorePort | None = None,  # 추가
) -> NormalizationMap:
    ...
    existing_map = map_store.load() if map_store else None
    normalized_results, norm_map = self._normalization.normalize(raw_results, existing_map)
    if map_store:
        map_store.save(norm_map)
    ...
```

### Phase 2 테스트 계획

| 테스트 | 핵심 검증 |
|---|---|
| `FileNormalizationMapStore` | save 후 load 시 동일한 mapping 반환 |
| `EntityNormalizationService.normalize(existing_map=...)` | 기존 canonical "BERT"가 있을 때 새 배치의 "bert"가 LLM 없이 "BERT"로 매핑됨 |
| `MethodGraphService.build_method_graph(map_store=...)` | 두 번 호출 시 두 번째 호출이 첫 번째 run의 map을 로드하여 사용함 |

---

## 전체 실행 순서

```
[Phase 1 - 현재]
Step 1-1: GraphRepositoryPort에 추상 메서드 추가
Step 1-2: Neo4jGraphRepository 구현 (get_all_method_names, merge_method_nodes)
Step 1-3: MethodDeduplicationService 신규 생성
Step 1-4: scripts/dedup_methods.py 신규 생성
  ↓ 테스트 통과 확인
  ↓ dry-run으로 병합 대상 확인
  ↓ 실제 실행으로 현재 DB 중복 정리

[Phase 2 - Phase 1 완료 후, 승인 후 진행]
Step 2-1: NormalizationMapStorePort 신규 생성
Step 2-2: FileNormalizationMapStore 구현
Step 2-3: EntityNormalizationService.normalize() 확장
Step 2-4: MethodGraphService.build_method_graph() 수정
```

---

## 업데이트 필요 문서

- `docs/STRUCTURE.md` — `method_deduplication_service.py`, `file_normalization_map_store.py`, `scripts/dedup_methods.py` 추가 반영
- `docs/STATUS.md` — Phase 1/2 진행 상황 업데이트
- `docs/TECHSPEC.md` — Normalization 전략 섹션 기술 (배치 내부 → 사후 제거 → 배치 간 예방)
