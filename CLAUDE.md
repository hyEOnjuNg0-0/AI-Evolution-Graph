# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI EvoGraph builds and analyzes a Citation/Method Evolution Graph of AI research papers. It uses GraphRAG-style extraction to map how AI methods evolve across papers over time.

**Goal**: Model the AI research ecosystem as a graph, quantifying research lineage, structural inflection points, and diffusion dynamics.

## Architecture

The project follows **Clean Architecture** with strict layer ordering. Dependencies flow inward only — outer layers depend on inner layers via Ports (interfaces).

```
Layer E — Interface (FastAPI + Next.js)
    ↓
Layer D — Analytical (Breakthrough/Trend analysis)
    ↓
Layer C — Ranking (Top-k, backbone extraction)
    ↓
Layer B — Retrieval (Vector, graph, hybrid)
    ↓
Layer A — Knowledge Graph (Citation + Method Evolution)
```

**Build bottom-up**: never implement a higher layer without the lower layer fully tested.

## Rules

Read docs/TECHSPEC.md and docs/STRUCTURE.md before conducting your work.
개발 후 디렉토리 구조가 변경될 시 반드시 docs/STRUCTURE.md에 변경 내용 명시
docs/STATUS.md에 진행 상황 메모

1. 구현 작업 원칙 
    - SOLID 원칙 사용
    - UI 이외의 핵심 로직은 TDD로 구현할 것
    - Clean Architecture를 사용해서 구현 : 책임과 관심사를 명확히 분리하여 구현
2. 코드 품질 원칙
    - 단순성 : 언제나 복잡한 솔루션보다 가장 단순한 솔루션을 우선시할 것
    - 중복 방지 : 코드 중복을 피하고, 가능한 기존 기능을 재사용할 것
    - 가드레일 : 테스트 외에는 개발이나 프로덕션 환경에서 모의 데이터를 사용하지 말 것
    - 효율성 : 명확성을 희생하지 않으면서 토큰 사용을 최소화하도록 출력을 최적화할 것
3. 리팩토링
    - 리팩토링이 필요한 경우 계획을 설명하고 허락 받은 다음 진행할 것
    - 코드 구조를 개선하는 것이 목표이며, 기능 변경이 되어선 안 됨
    - 리팩토링 후에는 모든 테스트가 통과하는지 확인할 것
4. 디버깅
    - 디버깅 시에는 원인 및 해결책을 설명하고 허락 받은 다음 진행
    - 에러 해결보다는 제대로 동작하는 것이 중요
    - 원인이 불분명할 경우 상세 로그를 추가할 것
5. 언어
    - 문서 한국어로 작성
    - 코드 주석 영어로 작성
    - 기술적인 용어나 라이브러리 이름 등은 원문 유지
6. 문서화
    - 주요 컴포넌트 개발 후에는 /docs/[component].md에 간략한 요약을 작성할 것
    - 문서는 코드와 함께 업데이트
    - 복잡한 로직이나 알고리즘은 주석으로 설명할 것