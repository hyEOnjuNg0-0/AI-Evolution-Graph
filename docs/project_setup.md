## 프로젝트 기반 설정 요약

Phase 0에서 아래 기반 구성을 완료했다.

- Python 패키지 스켈레톤 구성 (`src/aievograph`)
- 환경 변수 로딩 설정 (`pydantic-settings`)
- 공통 도메인 모델 정의 (`Paper`, `Author`, `Method`, `Citation`, `src/aievograph/domain/models.py`)
- 도메인 포트 인터페이스 추가 (`src/aievograph/domain/ports/graph_repository.py`)
    - 도메인 레이어가 “그래프 저장소에 무엇을 할지”만 선언하는 추상 계약(Port)
    - 도메인은 Neo4j 같은 구체 기술에 직접 의존하지 않고, 나중에 인프라 어댑터(예: Neo4jGraphRepository)가 이 인터페이스를 구현
- 공통 로깅 설정 추가(`src/aievograph/infrastructure/logging.py`)
- Neo4j Docker 실행 파일 추가 (`docker-compose.yml`)
    - 로컬에서 Neo4j를 컨테이너로 쉽게 띄우기 위한 실행 설정 파일
- 테스트 설정/샘플 단위 테스트 추가 (`pytest`, `pytest.ini`)
- CI 테스트 워크플로우 추가 (`.github/workflows/test.yml`)
    - GitHub 저장소에 push/PR 할 때 자동 실행
