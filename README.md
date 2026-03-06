# AI EvoGraph

AI 논문의 Citation/Method 진화 그래프를 구축하고 분석하기 위한 프로젝트입니다.

## 빠른 시작

1. Python 3.11 이상 환경 준비
2. 의존성 설치

```bash
pip install -e ".[dev]"
```

3. 환경 변수 파일 생성

```bash
cp .env.example .env
```

4. 테스트 실행

```bash
pytest
```

5. Neo4j 실행 (Docker)

```bash
docker compose up -d
```
