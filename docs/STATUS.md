# AI EvoGraph — 단계별 개발 계획서
---
## 프로젝트 목표

> AI 연구 생태계를 GraphRAG 기반의 그래프로 모델링하고, 연구 계보 구조, 구조적 전환점, 확산 동력 등을 정량적으로 분석하는 시스템을 구축

---

## 진행 상태

> 마지막 업데이트: 2026-02-27

| Phase | 레이어 | 상태 | 진행률 |
|-------|--------|------|--------|
| 0 | 프로젝트 기반 설정 | 🟢 완료 | 100% |
| 1 | Layer A-1 — Temporal Citation Graph | 🟡 진행 중 | 30% |
| 2 | Layer A-2 — Method Evolution Graph | 🔴 미착수 | 0% |
| 3 | Layer B — Retrieval | 🔴 미착수 | 0% |
| 4 | Layer C — Ranking | 🔴 미착수 | 0% |
| 5 | Layer D — Analytical | 🔴 미착수 | 0% |
| 6 | Layer E — Interface | 🔴 미착수 | 0% |
| 7 | 통합 및 실험 | 🔴 미착수 | 0% |

**상태 범례**: 🔴 미착수 · 🟡 진행 중 · 🟢 완료 · ⏸️ 보류

---

## 우선순위 및 예상 일정

| 레이어 | 핵심 마일스톤 | 의존성 | 상태 |
|--------|---------------|--------|--------|
| 기반 설정 | 프로젝트 스켈레톤 완성 | 없음 | 🟢 완료 |
| Layer A | Citation + Method Graph 구축 완료 | Phase 0 | 🔴 미착수 |
| Layer B | 3가지 Retrieval 전략 동작 확인 | Phase 1 | 🔴 미착수 |
| Layer C | Top-k ranking + backbone 추출 | Phase 2 | 🔴 미착수 |
| Layer D | Breakthrough + Trend 분석 동작 | Phase 1 (+ Phase 3 부분 활용) | 🔴 미착수 |
| Layer E | 웹 UI 완성 | Phase 2, 3, 4 | 🔴 미착수 |
| 통합/실험 | RQ1~3 실험 완료 | 전체 | 🔴 미착수 |
