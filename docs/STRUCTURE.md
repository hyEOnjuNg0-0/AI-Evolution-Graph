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
│       │   └── settings.py                    # AppSettings + TARGET_VENUES
│       ├── domain/
│       │   ├── ports/
│       │   │   ├── __init__.py
│       │   │   ├── graph_repository.py
│       │   │   └── paper_collector.py          # PaperCollectorPort (논문 수집 포트)
│       │   ├── services/
│       │   │   ├── __init__.py
│       │   │   └── paper_filter.py             # 연도별 top-N% 인용 필터링
│       │   ├── __init__.py
│       │   └── models.py
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   ├── logging.py
│       │   └── semantic_scholar_client.py      # Semantic Scholar Bulk API 어댑터
│       └── __init__.py
├── tests/
│   ├── test_domain_models.py
│   ├── test_semantic_scholar_client.py         # API 클라이언트 단위 테스트
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