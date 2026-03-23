# 임베딩 저장 파이프라인 추가 계획

> 작성일: 2026-03-23
> 상태: 계획 확정, 미착수

## 배경 및 문제 정의

`VectorRetrievalService.embed_and_store_papers()`와 `Neo4jVectorRepository`는 구현 완료되어 있으나,
`scripts/ingest.py`에 호출 단계가 없어 논문을 수집해도 embedding이 Neo4j에 저장되지 않는다.

`HybridRetrievalService.search()`는 내부적으로 항상 `VectorRetrievalService.search()`를 먼저 호출하므로,
embedding 없이는 seed가 없음 → 그래프 확장도 없음 → **빈 Subgraph 반환**.

현재 `ingest.py` 파이프라인:
```
논문 수집 → Citation Graph 구축 → (선택) Method Graph 구축
                                        ↑ embedding 저장 단계 없음
```

목표 파이프라인:
```
논문 수집 → Citation Graph 구축 → (선택) embedding 저장 → (선택) Method Graph 구축
```

---

## 이미 저장된 데이터 처리

Neo4j에 이미 Paper 노드가 존재하지만 `embedding` 속성이 없는 경우, **백필(backfill)** 이 필요하다.

`--method-graph-only`와 동일한 패턴으로 `--embed-only` 플래그를 추가한다:
- Neo4j에서 Paper 노드를 연도 범위로 조회
- `embed_and_store_papers()` 실행
- 새로운 논문 수집 없이 embedding만 저장

이렇게 하면 기존 데이터와 신규 데이터를 동일한 인터페이스로 처리할 수 있다.

---

## 변경 사항

### Step 1. `VectorRepositoryPort`에 `get_paper_ids_without_embedding` 추가

**파일**: `src/aievograph/domain/ports/vector_repository.py`

```python
@abstractmethod
def get_paper_ids_without_embedding(self) -> list[str]:
    """Return paper_ids of Paper nodes that have no embedding property."""
    raise NotImplementedError
```

**용도**: 이미 embedding이 있는 논문을 skip하여 불필요한 OpenAI API 비용을 방지한다.

---

### Step 2. `Neo4jVectorRepository`에 구현 추가

**파일**: `src/aievograph/infrastructure/neo4j_vector_repository.py`

**Cypher**:
```cypher
MATCH (p:Paper)
WHERE p.embedding IS NULL
RETURN p.paper_id
```

---

### Step 3. `VectorRetrievalService.embed_and_store_papers()`에 skip 로직 추가

**파일**: `src/aievograph/domain/services/vector_retrieval_service.py`

> **이 변경은 기존 동작 중인 코드를 수정합니다. 진행 전 승인이 필요합니다.**

`embed_and_store_papers()` 내부에서 `vector_repo.get_paper_ids_without_embedding()`으로
embedding이 없는 논문만 필터링하여 처리한다:

```python
def embed_and_store_papers(self, papers, batch_size=...):
    self._vector_repo.create_vector_index()              # 인덱스 보장
    ids_without = set(self._vector_repo.get_paper_ids_without_embedding())
    papers_to_embed = [p for p in papers if p.paper_id in ids_without]
    if not papers_to_embed:
        logger.info("All papers already have embeddings. Nothing to do.")
        return
    logger.info("%d / %d papers need embedding.", len(papers_to_embed), len(papers))
    # 기존 배치 처리 로직 (papers_to_embed 대상)
    ...
```

이 변경으로 두 가지를 동시에 해결한다:
- 인덱스 초기화 패턴 불일치 해소 (`create_vector_index()` 자동 호출)
- 재실행 시 이미 embedding된 논문 skip → OpenAI 비용 절감

이후 `scripts/inspection/check_retrieval.py`의 수동 `create_vector_index()` 호출은 제거 가능.

---

### Step 4. `ingest.py`에 `--embed` / `--embed-only` 플래그 추가

> `_build_embeddings()`에 전달되는 `papers`는 전체 목록이어도 무방하다.
> Step 3의 skip 로직이 서비스 내부에서 처리하므로 호출자는 필터링을 신경 쓸 필요 없다.

**파일**: `scripts/ingest.py`

**새 플래그**:

| 플래그 | 동작 |
|---|---|
| `--embed` | 수집한 논문의 embedding을 생성하여 Neo4j에 저장 (Citation Graph 직후) |
| `--embed-only` | 논문 수집 skip, Neo4j에서 논문 로드 후 embedding만 저장 (백필용) |

**`_build_embeddings()` 헬퍼 추가** (`_build_method_graph()` 패턴과 동일):

```python
def _build_embeddings(vector_repo, papers, settings):
    openai_client = OpenAI(api_key=settings.openai_api_key)
    embedding_client = OpenAIEmbeddingClient(openai_client)
    vector_service = VectorRetrievalService(embedding_client, vector_repo)
    vector_service.embed_and_store_papers(papers)
```

**`main()` 흐름 변경**:

```
# --embed-only 분기 (기존 --method-graph-only 패턴과 동일)
if args.embed_only:
    papers = repo.get_papers_by_year_range(year_start, year_end)
    _build_embeddings(vector_repo, papers, settings)
    return

# 기존 normal mode에 추가
service.build_citation_graph(papers)        # 기존
if args.embed:
    _build_embeddings(vector_repo, papers, settings)   # 추가
if args.method_graph:
    _build_method_graph(repo, papers, ...)  # 기존
```

**`Neo4jVectorRepository` 인스턴스화 위치**: `driver` 생성 직후, `Neo4jGraphRepository`와 나란히.

---

## 전체 실행 순서

```
[신규 데이터 수집 + embedding]
python scripts/ingest.py --embed

[기존 데이터 백필 (이미 Neo4j에 있는 논문)]
python scripts/ingest.py --embed-only --year-start 2018 --year-end 2024

[신규 수집 + citation graph + embedding + method graph 전체]
python scripts/ingest.py --embed --method-graph
```

---

## 영향 범위

| 파일 | 변경 유형 |
|---|---|
| `scripts/ingest.py` | `--embed` / `--embed-only` 플래그 추가, `_build_embeddings()` 추가 |
| `src/aievograph/domain/services/vector_retrieval_service.py` | `embed_and_store_papers()` 첫 줄에 `create_vector_index()` 추가 |
| `src/aievograph/domain/ports/vector_repository.py` | `get_paper_ids_without_embedding()` 추가 |
| `src/aievograph/infrastructure/neo4j_vector_repository.py` | 위 포트 구현 |
| `scripts/inspection/check_retrieval.py` | 수동 `create_vector_index()` 호출 제거 (Step 4 완료 후) |

---

## 업데이트 필요 문서

- `docs/STATUS.md` — Layer B 실질 완료 조건에 embedding 저장 포함
- `docs/STRUCTURE.md` — `ingest.py` 플래그 목록 업데이트
