## 기술 스택

| 영역 | 기술 | 버전/사양 | 용도 |
|------|------|-----------|------|
| **언어** | Python | 3.11+ | 백엔드 전체 |
| **그래프 DB** | Neo4j | 5.x | Citation/Method 그래프 저장, Cypher 쿼리, GDS 라이브러리 |
| **벡터 검색** | Neo4j Vector Index | (내장) | Embedding 기반 유사도 검색 (별도 벡터 DB 불필요) |
| **오케스트레이션** | LangGraph | latest | 멀티스텝 RAG 파이프라인, 상태 기반 워크플로우 |
| **LLM** | OpenAI GPT-4o | — | Entity extraction, Relation extraction, 요약 |
| **Embedding** | OpenAI text-embedding-3-small | — | Vector retrieval용 논문 임베딩 |
| **논문 API** | Semantic Scholar | Bulk API v1 | 논문 메타데이터, citation/reference 데이터 수집 |
| **백엔드 API** | FastAPI | latest | 프론트엔드-백엔드 통신 |
| **프론트엔드** | Next.js | latest | 웹 인터페이스 |
| **UI 라이브러리** | TailwindCSS + ShadCN | latest | 스타일링 및 컴포넌트 |
| **배포** | Vercel | — | 프론트엔드 배포 |
| **테스트** | pytest | latest | TDD, 단위/통합 테스트 |
| **패키지 관리** | uv 또는 Poetry | latest | Python 의존성 관리 |