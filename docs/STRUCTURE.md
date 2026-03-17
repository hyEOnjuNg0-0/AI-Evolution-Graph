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
│       │   │   ├── paper_collector.py          # PaperCollectorPort (논문 수집 포트)
│       │   │   ├── method_extractor.py         # MethodExtractorPort (LLM 추출 포트)
│       │   │   └── entity_normalizer.py        # EntityNormalizerPort (엔티티 정규화 포트)
│       │   ├── services/
│       │   │   ├── __init__.py
│       │   │   ├── citation_graph_service.py   # CitationGraphService (Citation Graph 구축 서비스)
│       │   │   ├── paper_filter.py             # 논문 수집 전처리 필터 (연도별 top-N% 인용 수 기준으로 노이즈 제거)
│       │   │   ├── method_extraction_service.py # MethodExtractionService (추출 조율 서비스)
│       │   │   ├── entity_normalization_service.py # EntityNormalizationService (전역 정규화 서비스)
│       │   │   └── method_graph_service.py     # MethodGraphService (추출→정규화→저장 오케스트레이션)
│       │   ├── __init__.py
│       │   └── models.py                       # 도메인 모델 (Author, Paper, Citation, Method, MethodRelation, ExtractionResult)
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   ├── logging.py
│       │   ├── neo4j_graph_repository.py       # Neo4jGraphRepository (GraphRepositoryPort 구현체)
│       │   ├── arxiv_client.py                 # arXiv API 어댑터 (카테고리별 수집 + S2 enrichment)
│       │   ├── semantic_scholar_client.py      # Semantic Scholar Bulk API 어댑터
│       │   ├── llm_method_extractor.py         # LLMMethodExtractor (structured output + gleaning, OpenAI 구현체)
│       │   └── llm_entity_normalizer.py        # LLMEntityNormalizer (문자열 유사도 클러스터링 + LLM 판단)
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
│   ├── test_settings.py
│   ├── test_method_extraction_service.py       # MethodExtractionService 단위 테스트
│   ├── test_llm_method_extractor.py            # LLMMethodExtractor 단위 테스트 (OpenAI client mock)
│   ├── test_entity_normalization_service.py    # EntityNormalizationService 단위 테스트
│   ├── test_llm_entity_normalizer.py           # LLMEntityNormalizer + _find_candidate_clusters 단위 테스트
│   └── test_method_graph_service.py            # MethodGraphService 단위 테스트
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