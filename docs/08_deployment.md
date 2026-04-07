# Phase 8 — 배포 계획

> 마지막 업데이트: 2026-04-07

---

## 1. 배포 대상 개요

| 컴포넌트 | 설명 | 기술 |
|----------|------|------|
| Frontend | 웹 UI | Next.js 16 (App Router) |
| Backend | REST API 서버 | FastAPI (Python 3.11+) |
| Database | 그래프 + 벡터 인덱스 | Neo4j 5.x + GDS 플러그인 |
| Ingest | 논문 수집 배치 스크립트 | `scripts/ingest.py` (일회성/수동) |

---

## 2. 배포 아키텍처

```
[사용자 브라우저]
       │  HTTPS
       ▼
[Vercel — Next.js]
       │  HTTPS (NEXT_PUBLIC_API_URL)
       ▼
[Railway — FastAPI 컨테이너]
       │  Bolt (NEO4J_URI)
       ▼
[Hetzner VPS — Neo4j + GDS]
```

---

## 3. 컴포넌트별 추천 플랫폼

### 3.1 Frontend → **Vercel**

- Next.js 공식 배포 플랫폼, App Router 완전 지원
- GitHub push → 자동 프리뷰 배포 + 프로덕션 배포
- Free 플랜으로 충분 (Hobby: 100GB 대역폭/월)
- 환경 변수: `NEXT_PUBLIC_API_URL` 설정

```bash
# 배포 명령 (Vercel CLI)
vercel --prod
```

### 3.2 Backend → **Railway**

**추천 이유**: Docker 컨테이너 그대로 배포, GitHub 연동 CD, 무중단 배포 지원, 저렴한 비용

- Starter 플랜: ~$5/월 (500시간, 512MB RAM)
- `Dockerfile` 또는 `Procfile` 기반 배포
- 환경 변수 대시보드에서 관리
- 자동 HTTPS 엔드포인트 발급

**대안**: Render (비슷한 가격대), Fly.io (컨테이너 직접 제어)

```dockerfile
# Dockerfile (신규 생성 필요)
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install uv && uv sync --no-dev
COPY src/ src/
CMD ["uvicorn", "aievograph.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.3 Neo4j → **자체 호스팅 (Hetzner VPS)**

**Neo4j Aura를 사용하지 않는 이유**: GDS(Graph Data Science) 플러그인이 Aura Free에서 미지원이며, Professional 플랜은 고비용. 이 프로젝트는 GDS PageRank/Betweenness 연산이 핵심이므로 자체 호스팅이 현실적.

**추천 서버**: Hetzner CX21 (2vCPU, 4GB RAM) — €4.15/월
- Neo4j 공식 Docker 이미지 + GDS 플러그인 포함
- 영구 볼륨으로 데이터 보존
- Bolt(7687), HTTP(7474) 포트 외부 노출 (방화벽으로 Railway IP만 허용 권장)

```bash
# 서버 초기 설정 (docker-compose 활용)
# docker-compose.yml 프로덕션 버전 → 아래 4.1절 참고
docker compose up -d neo4j
```

**대안**: DigitalOcean Droplet $12/월 (2vCPU, 2GB RAM), Fly.io (persistent volume)

---

## 4. 설정 파일 준비

### 4.1 `docker-compose.prod.yml` (Neo4j 서버용)

현재 `docker-compose.yml`에서 프로덕션에 맞게 아래 항목 수정:

```yaml
services:
  neo4j:
    image: neo4j:5
    restart: always
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
      - NEO4J_PLUGINS=["graph-data-science"]
      - NEO4J_server_memory_heap_initial__size=1G
      - NEO4J_server_memory_heap_max__size=2G
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
```

### 4.2 `Dockerfile` (Backend용, 신규 생성)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency spec and install (production only)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ src/

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "aievograph.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 5. 환경 변수 목록

| 변수 | 위치 | 설명 |
|------|------|------|
| `NEO4J_URI` | Railway | `bolt://<hetzner-ip>:7687` |
| `NEO4J_USER` | Railway | `neo4j` |
| `NEO4J_PASSWORD` | Railway | Neo4j 비밀번호 |
| `OPENAI_API_KEY` | Railway | OpenAI API 키 |
| `S2_API_KEY` | Railway (ingest 시만 필요) | Semantic Scholar API 키 |
| `NEXT_PUBLIC_API_URL` | Vercel | `https://<railway-도메인>` |

> 로컬: `.env` 파일 (`.env.example` 참고)
> 프로덕션: 각 플랫폼 대시보드에서 직접 설정 (절대 코드에 하드코딩 금지)

---

## 6. CI/CD 파이프라인

현재 `.github/workflows/test.yml`에 테스트 자동화가 있음. 배포 단계 추가:

```
main 브랜치 push
  │
  ├─ [test.yml] pytest 실행 (기존)
  │
  └─ [deploy.yml] (신규, 아래 참고)
       ├─ Frontend: Vercel GitHub 연동으로 자동 배포 (별도 설정 불필요)
       └─ Backend: Railway GitHub 연동으로 자동 배포 (별도 설정 불필요)
```

Vercel과 Railway 모두 GitHub 레포 연동 시 `main` 브랜치 push에서 자동 배포됨 — 별도 workflow 파일 불필요.

---

## 7. 데이터 수집 (Ingest) 전략

`scripts/ingest.py`는 일회성 배치 작업으로, 배포된 서버에서 직접 실행하지 않음.

**권장 절차**:

1. 로컬 환경에서 `.env`에 프로덕션 `NEO4J_URI`를 가리키도록 설정
2. `python scripts/ingest.py --embed --method-graph` 실행
3. 데이터가 Hetzner VPS의 Neo4j에 직접 적재됨

```bash
# 예시: 프로덕션 Neo4j에 데이터 수집
NEO4J_URI=bolt://<hetzner-ip>:7687 python scripts/ingest.py \
  --venues NeurIPS ICML ICLR \
  --year-start 2018 --year-end 2024 \
  --embed --method-graph
```

> 주의: 수집 중 백엔드 API가 중단되지 않으며 읽기 요청은 정상 처리됨 (Neo4j는 MVCC 지원)

---

## 8. 단계별 배포 절차

### Step 1 — Neo4j 서버 세팅 (Hetzner)

1. Hetzner Cloud 계정 생성 → CX21 서버 생성 (Ubuntu 24.04)
2. Docker + Docker Compose 설치
3. `docker-compose.prod.yml` 업로드 후 `docker compose up -d`
4. 방화벽: 7687 포트를 Railway 서비스 IP로만 허용, 7474는 관리 목적으로 제한적 허용
5. 로컬에서 연결 확인: `cypher-shell -a bolt://<ip>:7687 -u neo4j -p <pw>`

### Step 2 — 데이터 수집

1. 로컬 `.env`에서 `NEO4J_URI`를 프로덕션 Hetzner IP로 변경
2. `python scripts/ingest.py ...` 실행 (수 시간 소요 예상)
3. Neo4j Browser(`http://<ip>:7474`)에서 데이터 확인

### Step 3 — Backend 배포 (Railway)

1. Railway 계정 생성 → New Project → "Deploy from GitHub repo" 선택
2. 환경 변수 설정 (섹션 5 참고)
3. `Dockerfile` 생성 후 배포 트리거
4. `/health` 엔드포인트 응답 확인

### Step 4 — Frontend 배포 (Vercel)

1. Vercel 계정 생성 → "Add New Project" → GitHub 레포 연결
2. Root Directory: `frontend`
3. `NEXT_PUBLIC_API_URL` 환경 변수에 Railway 도메인 입력
4. Deploy → 자동 빌드 완료 확인

### Step 5 — 통합 검증

- `POST /api/lineage` 요청이 정상 응답하는지 확인
- Frontend에서 쿼리 실행 → 그래프 렌더링 확인
- CORS 오류 없는지 확인 (`api/main.py`의 `allow_origins`에 Vercel 도메인 포함 여부)

---

## 9. 예상 비용

| 항목 | 플랫폼 | 월 비용 |
|------|--------|---------|
| Frontend | Vercel Hobby | 무료 |
| Backend | Railway Starter | ~$5 |
| Neo4j | Hetzner CX21 | €4.15 (~$5) |
| OpenAI (API) | 사용량 기반 | $5–20 (쿼리 빈도에 따라 다름) |
| **합계** | | **~$15–30/월** |

> Ingest용 OpenAI 비용(임베딩 + LLM 추출)은 초기 1회성 비용으로 별도 계산.

---

## 10. CORS 수정 필요 사항

배포 전 `src/aievograph/api/main.py`의 `allow_origins`에 실제 Vercel 도메인 추가:

```python
allow_origins=[
    "http://localhost:3000",
    "https://*.vercel.app",
    "https://<실제-vercel-도메인>.vercel.app",  # 확정 도메인 추가
],
```
