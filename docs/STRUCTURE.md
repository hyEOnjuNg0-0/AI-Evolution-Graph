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


│       │   │   ├── entity_normalizer.py        # EntityNormalizerPort (엔티티 정규화 포트)


│       │   │   ├── normalization_map_store.py  # NormalizationMapStorePort (정규화 맵 영속성 포트)


│       │   │   ├── embedding_port.py           # EmbeddingPort (텍스트 임베딩 생성 포트)


│       │   │   ├── vector_repository.py        # VectorRepositoryPort (벡터 인덱스 포트)


│       │   │   ├── centrality_repository.py    # CentralityRepositoryPort (GDS 중심성 계산 포트)


│       │   │   ├── paper_embedding_repository.py # PaperEmbeddingRepositoryPort (논문 embedding 조회 포트)


│       │   │   ├── subgraph_edge_repository.py   # SubgraphEdgeRepositoryPort (subgraph 내 citation edge 조회 포트)
│       │   │   ├── citation_time_series_repository.py # CitationTimeSeriesRepositoryPort (연도별 citation count 조회 포트, Layer D Step 5.1)
│       │   │   ├── method_trend_repository.py # MethodTrendRepositoryPort (method 연도별 사용량·venue 분포 조회 포트, Layer D Step 5.2)
│       │   │   └── method_evolution_repository.py # MethodEvolutionRepositoryPort (method 관계 엣지·paper→method 매핑 포트, Layer D Step 5.3)

│       │   ├── services/


│       │   │   ├── __init__.py


│       │   │   ├── citation_graph_service.py   # CitationGraphService (Citation Graph 구축 서비스)


│       │   │   ├── method_extraction_service.py # MethodExtractionService (추출 조율 서비스)


│       │   │   ├── entity_normalization_service.py # EntityNormalizationService (전역 정규화 서비스)


│       │   │   ├── method_graph_service.py     # MethodGraphService (추출→정규화→저장 오케스트레이션)


│       │   │   ├── method_deduplication_service.py # MethodDeduplicationService (사후 중복 Method 노드 병합)


│       │   │   ├── vector_retrieval_service.py # VectorRetrievalService (임베딩 생성·저장·유사도 검색, Layer B Step 3.1)


│       │   │   ├── graph_retrieval_service.py  # GraphRetrievalService (N-hop citation 확장 검색, Layer B Step 3.2)


│       │   │   ├── hybrid_retrieval_service.py # HybridRetrievalService (α×semantic + β×graph 점수 기반 Subgraph, Layer B Step 3.3)


│       │   │   ├── centrality_ranking_service.py # CentralityRankingService (GDS PageRank+Betweenness 기반 구조적 중요도 랭킹, Layer C Step 4.1)


│       │   │   ├── embedding_ranking_service.py # EmbeddingRankingService (쿼리-논문 cosine 유사도 기반 의미적 랜킹, Layer C Step 4.2)


│       │   │   ├── combined_ranking_service.py  # CombinedRankingService (centrality+semantic 결합 랜킹 + backbone 추출, Layer C Step 4.3)
│       │   │   ├── breakthrough_detection_service.py # BreakthroughDetectionService (Kleinberg burst + centrality shift 기반 breakthrough 탐지, Layer D Step 5.1)
│       │   │   ├── trend_momentum_service.py # TrendMomentumService (CAGR + Shannon entropy + adoption velocity 기반 method trend 점수, Layer D Step 5.2)
│       │   │   └── evolution_path_service.py # EvolutionPathService (Method Evolution Graph 경로 추출 + 분기점 + 영향력 점수, Layer D Step 5.3)

│       │   ├── utils/


│       │   │   ├── __init__.py


│       │   │   ├── paper_filter.py             # 논문 수집 전처리 필터 (연도별 top-N% 인용 수 기준으로 노이즈 제거)

│       │   │   ├── ranking_utils.py            # 점수 정규화 유틸리티 (normalize_scores)
│       │   │   ├── score_utils.py              # 점수 결합 유틸리티 (combine_scores: normalize + weighted sum)
│       │   │   ├── graph_utils.py              # DAG 경로 추출 유틸리티 (extract_dag_paths: exhaustive DFS)
│       │   │   └── validation_utils.py         # 파라미터 검증 유틸리티 (validate_unit_weights, validate_positive_int)


│       │   ├── __init__.py


│       │   └── models.py                       # 도메인 모델 (Author, Paper, Citation, Method, MethodRelation, ExtractionResult)


│       ├── infrastructure/


│       │   ├── __init__.py


│       │   ├── logging.py


│       │   ├── file_cache.py                   # JSON 파일 캐시·체크포인트 공유 유틸리티 (read_json, write_json, checkpoint_path 등)


│       │   ├── http_utils.py                   # HTTP 재시도 공유 유틸리티 (request_with_retry, 지수 백오프)


│       │   ├── neo4j_graph_repository.py       # Neo4jGraphRepository (GraphRepositoryPort 구현체)


│       │   ├── neo4j_vector_repository.py      # Neo4jVectorRepository (VectorRepositoryPort 구현체)


│       │   ├── openai_embedding_client.py      # OpenAIEmbeddingClient (EmbeddingPort 구현체, text-embedding-3-small)


│       │   ├── arxiv_client.py                 # arXiv API 어댑터 (카테고리별 수집 + S2 enrichment)


│       │   ├── semantic_scholar_client.py      # Semantic Scholar Bulk API 어댑터


│       │   ├── llm_method_extractor.py         # LLMMethodExtractor (structured output + gleaning, OpenAI 구현체)


│       │   ├── llm_entity_normalizer.py        # LLMEntityNormalizer (문자열 유사도 클러스터링 + LLM 판단)


│       │   ├── file_normalization_map_store.py # FileNormalizationMapStore (NormalizationMapStorePort 구현체, data/normalization_map.json)


│       │   ├── neo4j_centrality_repository.py  # Neo4jCentralityRepository (CentralityRepositoryPort 구현체, GDS 2.1+)


│       │   ├── neo4j_paper_embedding_repository.py # Neo4jPaperEmbeddingRepository (PaperEmbeddingRepositoryPort 구현체, 논문 embedding 조회)


│       │   ├── neo4j_subgraph_edge_repository.py # Neo4jSubgraphEdgeRepository (SubgraphEdgeRepositoryPort 구현체, subgraph 내 citation edge 조회)
│       │   ├── neo4j_citation_time_series_repository.py # Neo4jCitationTimeSeriesRepository (CitationTimeSeriesRepositoryPort 구현체, 연도별 citation count 조회)
│       │   ├── neo4j_method_trend_repository.py # Neo4jMethodTrendRepository (MethodTrendRepositoryPort 구현체, USES 엣지 집계)
│       │   ├── neo4j_method_evolution_repository.py # Neo4jMethodEvolutionRepository (MethodEvolutionRepositoryPort 구현체, method 관계·paper-method 매핑)
│       │   └── neo4j_utils.py              # Neo4j 공유 쿼리 유틸리티 (run_grouped_query: nested dict 누적 패턴)

│       ├── api/                             # Layer E — FastAPI application
│       │   ├── __init__.py
│       │   ├── main.py                      # FastAPI app + CORS + router registration
│       │   ├── dependencies.py              # DI factories: service wiring for route handlers
│       │   ├── routers/
│       │   │   ├── __init__.py
│       │   │   ├── lineage.py               # POST /api/lineage (Research Lineage Exploration)
│       │   │   ├── breakthrough.py          # POST /api/breakthrough (Breakthrough Detection)
│       │   │   ├── trend.py                 # POST /api/trend (Trending Methods Discovery — top-k, no topic)
│       │   │   └── evolution.py             # POST /api/evolution (Method Evolution Path — fuzzy search + DAG)
│       │   └── schemas/
│       │       ├── __init__.py
│       │       ├── lineage.py               # LineageRequest / LineageResponse
│       │       ├── breakthrough.py          # BreakthroughRequest / BreakthroughResponse
│       │       ├── trend.py                 # TrendRequest / TrendResponse (Discovery: start_year, end_year, top_k → methods[])
│       │       └── evolution.py             # EvolutionRequest / EvolutionResponse (method_name → evolution_path + yearly_counts)
│
│       └── __init__.py


├── frontend/                                # Layer E — Next.js frontend
│   ├── app/                                 # Next.js App Router pages
│   │   ├── lineage/page.tsx
│   │   ├── breakthrough/page.tsx
│   │   ├── trend/page.tsx
│   │   └── evolution/page.tsx               # Method Evolution Path page (신규)
│   ├── components/ui/                       # ShadCN UI components
│   ├── components/
│   │   ├── ui/                              # ShadCN UI primitives (button, card, input, …)
│   │   ├── lineage-query-panel.tsx          # Step 6.2: Research Lineage Exploration Query Panel
│   │   ├── graph-view-panel.tsx             # Step 6.3: Citation Graph SVG + Evolution Path DAG (evolutionResult prop)
│   │   ├── main-view.tsx                    # Step 6.5: 3-panel shell — lineage query | graph | evidence (shared selectedPaper state)
│   │   ├── evidence-panel.tsx               # Step 6.5: Evidence Panel — hybrid score breakdown + Semantic Scholar link
│   │   ├── breakthrough-view.tsx            # Step 6.4: Breakthrough Detection UI (form + bar chart + table)
│   │   ├── trend-view.tsx                   # Trending Methods Discovery UI (year range + top-k table/chart)
│   │   └── evolution-view.tsx               # Method Evolution Path UI (method search + DAG via GraphViewPanel)
│   ├── lib/
│   │   ├── api.ts                           # Typed API client (fetch wrappers)
│   │   └── utils.ts                         # ShadCN utility (cn)
│   ├── .env.local.example                   # NEXT_PUBLIC_API_URL template
│   ├── components.json                      # ShadCN configuration
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── package.json

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


│   ├── test_method_graph_service.py            # MethodGraphService 단위 테스트


│   ├── test_openai_embedding_client.py         # OpenAIEmbeddingClient 단위 테스트 (OpenAI client mock)


│   ├── test_vector_retrieval_service.py        # VectorRetrievalService 단위 테스트


│   ├── test_graph_retrieval_service.py         # GraphRetrievalService 단위 테스트


│   ├── test_hybrid_retrieval_service.py        # HybridRetrievalService 단위 테스트


│   ├── test_centrality_ranking_service.py      # CentralityRankingService 단위 테스트


├── test_embedding_ranking_service.py       # EmbeddingRankingService 단위 테스트


└── test_combined_ranking_service.py      # CombinedRankingService 단위 테스트

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


├── scripts/


│   ├── ingest.py                               # 논문 수집·그래프 구축 CLI


│   └── dedup_methods.py                        # Method 노드 사후 중복 제거 CLI (--dry-run 지원)


├── .env.example


├── .gitignore


├── docker-compose.yml


├── pyproject.toml


├── pytest.ini


└── README.md


```