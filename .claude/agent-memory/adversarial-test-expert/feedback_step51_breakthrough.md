---
name: Step 5.1 Breakthrough Detection - Vulnerabilities Found
description: Adversarial testing of BreakthroughDetectionService reveals 5 critical/high/medium bugs
type: feedback
---

# Step 5.1 — Breakthrough Detection Adversarial Testing Report

**Date**: 2026-03-26
**Status**: MAJOR GAPS — 1 Critical Bug + TDD Violation + 3 High/Medium Issues
**Implementation**: src/aievograph/domain/services/breakthrough_detection_service.py

## Critical Vulnerability

### CRASH BUG: Negative Citation Counts Trigger math.lgamma Domain Error
**Severity**: CRITICAL  
**Location**: _poisson_neg_log_prob() line 57, via _kleinberg_burst_score()  
**Root Cause**: No validation that k >= 0 before math.lgamma(k + 1)  
**Trigger**: Repository returns negative citation counts (data corruption, query bug)  
**Reproducible**: detect(["p1"], 2020, 2025) where repo returns {2020: -10, 2021: 20}  
**Crash Stack**: ValueError: math domain error at math.lgamma(-9)  
**Expected**: Graceful failure (skip paper, return 0.0, or raise ValueError with context)

---

## High Severity Issues

### 1. TDD VIOLATION: Zero Unit Tests for Layer D Core Logic
**Severity**: HIGH  
**Location**: tests/ directory completely missing test_breakthrough_detection_service.py  
**Contract Violation**: CLAUDE.md line 43: "UI 이외의 핵심 로직은 TDD로 구현할 것"  
**Status**: Step 5.1 marked 100% complete but untested  
**Impact**: No proof that Kleinberg burst, centrality shift, or normalization work correctly  
**Functions with zero coverage**:
- _kleinberg_burst_score() (Kleinberg Viterbi burst detection)
- _viterbi_states() (dynamic programming backtracking)
- _centrality_shift_score() (time-window split calculation)
- BreakthroughDetectionService.detect() (entire main service)

### 2. No Repository Output Validation
**Severity**: HIGH  
**Location**: detect() lines 241-243  
**Issue**: Service assumes CitationTimeSeriesRepositoryPort returns valid dict[str, dict[int, int]]  
**No checks for**:
  - Non-integer counts (floats accepted, may cause numerical issues)
  - Negative counts (crashes at lgamma)
  - Non-numeric types (runtime error)
  - Unexpected paper_ids in response (silently ignored, acceptable)

**Defensive Fix Needed**: Validate all counts are non-negative integers

---

## Medium Severity Issues

### 3. Recency Weight Formula Under-Documented
**Severity**: MEDIUM  
**Location**: _kleinberg_burst_score() lines 150-156  
**Issue**: Docstring doesn't explain recency weighting interpretation  
**Formula**: recency_weights = [1.0 + t / max(T-1, 1) for t in range(T)]  
**Ambiguity**: 
  - Why linearly scale 1.0 to 2.0?
  - Does this match Kleinberg's original paper?
  - What does "2x weight for newest year vs oldest" mean for burst detection?
**Impact**: Maintainers uncertain about mathematical soundness

### 4. Parameter Contract Incomplete
**Severity**: MEDIUM  
**Location**: detect() docstring  
**Missing Documentation**:
  - Alpha weight direction: is alpha=1.0 "burst only" or "shift only"? (Answer: burst-only)
  - Clipping negative shifts: why are declining papers not breakthroughs? (Answer: explicit design choice, but not documented)
  - Top_k behavior when top_k > len(paper_ids) (returns all, acceptable but not stated)
  - Repository contract edge case: when might papers be absent from returned dict (only zero citations, acceptable but subtle)

---

## Test Results Summary

### Tested via Adversarial Analysis (No formal test suite exists):

**Working Correctly**:
- Empty paper_ids → returns []
- Parameter validation: alpha, s, gamma, top_k, year_range validation works
- Repository missing papers → treated as zero citations
- All papers zero citations → all scores 0.0
- Sorting by breakthrough_score descending with paper_id tiebreaker
- Negative centrality_shift clipped to 0
- Alpha extremes (0.0 = shift-only, 1.0 = burst-only)
- Large time windows (T=100) handle correctly

**Not Tested (Vulnerabilities Found)**:
- Negative citation counts → CRASHES
- Float citation counts → accepted (may cause numerical drift)
- Repository returning unexpected paper_ids → silently ignored (may hide data loss)
- math.lgamma numerical stability with very large n_total
- Malformed paper_ids in input list

### Coverage by Function:
- _poisson_neg_log_prob: ✗ UNTESTED (negative k vulnerability found)
- _viterbi_states: PARTIALLY TESTED (basic correctness verified, edge cases not in test suite)
- _kleinberg_burst_score: ✗ UNTESTED
- _centrality_shift_score: ✗ UNTESTED  
- normalize_scores: ✓ VERIFIED (indirectly via service calls)
- BreakthroughDetectionService.detect: ✗ UNTESTED

---

## Architectural Assessment

**Layer D Compliance**: ✓ No layer violations detected
- Correctly depends only on CitationTimeSeriesRepositoryPort (Layer A port)
- Uses ranking_utils.normalize_scores from Layer C (allowed)

**TDD Mandate Compliance**: ✗ VIOLATION
- Core analytical layer implemented without unit tests
- Requirement: "UI 이외의 핵심 로직은 TDD로 구현할 것"
- Status: Step 5.1 marked complete, but proof of correctness missing

---

## How to Apply (Priority Order)

**Priority 1 (FIX CRITICAL BUG)**:
- Add validation in _kleinberg_burst_score or _viterbi_states: ensure all counts >= 0
- Either sanitize (clip negatives to 0) OR fail fast with ValueError with context
- Test: send negative counts, verify graceful handling

**Priority 2 (CREATE TEST SUITE - TDD MANDATE)**:
- Write tests/test_breakthrough_detection_service.py with 50+ test cases
- Cover: parameter validation, Viterbi correctness, centrality shift edge cases
- Cover: normalization, sorting, repository contract violations
- Run before proceeding to Step 5.2

**Priority 3 (ADD DEFENSIVE VALIDATION)**:
- Validate repository output at entry to detect()
- Check all counts are non-negative integers
- Fail fast with clear error messages, not math crashes

**Priority 4 (DOCUMENT PARAMETERS)**:
- Clarify alpha semantics (alpha=1 is burst-only, alpha=0 is shift-only)
- Explain negative shift clipping rationale
- Add reference to Kleinberg paper for burst detection algorithm

