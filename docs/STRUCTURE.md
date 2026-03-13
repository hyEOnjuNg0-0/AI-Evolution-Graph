## 디렉토리 구조
```
AiEvoGraph/
├── .github/
│   └── workflows/
│       └── test.yml
├── src/
│   └── aievograph/
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py                    # AppSettings + TARGET_VENUES + TARGET_ARXIV_CATEGORIES
│       ├── domain/
│       │   ├── ports/
│       │   │   ├── __init__.py
│       │   │   ├── graph_repository.py         # GraphRepositoryPort (Neo4j 추상 인터페이스)
│       │   │   └── paper_collector.py          # PaperCollectorPort (논문 수집 포트)
│       │   ├── services/
│       │   │   ├── __init__.py
│       │   │   ├── citation_graph_service.py   # CitationGraphService (그래프 구축 서비스)
│       │   │   └── paper_filter.py             # 연도별 top-N% 인용 필터링
│       │   ├── __init__.py
│       │   └── models.py                       # 논문 데이터 모델 정의 (Author, Paper, Citation, Method)
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   ├── logging.py
│       │   ├── neo4j_graph_repository.py       # Neo4jGraphRepository (GraphRepositoryPort 구현체)
│       │   ├── arxiv_client.py                 # arXiv API 어댑터 (카테고리별 수집 + S2 enrichment)
│       │   └── semantic_scholar_client.py      # Semantic Scholar Bulk API 어댑터
│       └── __init__.py
├── tests/
│   ├── integration/
│   │   └── test_pipeline.py                    # 통합 테스트: Neo4j 파이프라인 (pytest -m integration)
│   ├── test_citation_graph_service.py          # CitationGraphService 단위 테스트
│   ├── test_domain_models.py
│   ├── test_neo4j_graph_repository.py          # Neo4jGraphRepository 단위 테스트
│   ├── test_arxiv_client.py                    # arXiv 클라이언트 단위 테스트
│   ├── test_semantic_scholar_client.py         # S2 클라이언트 단위 테스트
│   ├── test_paper_filter.py                    # 필터링 로직 단위 테스트
│   └── test_settings.py
├── docs/
│   ├── 00_setup.md
│   ├── 01_TemporalCitationGraph.md
│   ├── 02_MethodEvolutionGraph.md
│   ├── 03_retrieval.md
│   ├── 04_ranking.md
│   ├── 05_analytical.md
│   ├── 06_inerface.md
│   ├── 07_experiment.md
│   ├── STATUS.md
│   ├── STRUCTURE.md
│   ├── TECHSPEC.md
│   └── project_setup.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── pyproject.toml
├── pytest.ini
└── README.md
```