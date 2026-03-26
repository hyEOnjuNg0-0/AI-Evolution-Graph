---
name: Step 5.2 Trend Momentum Critical Findings
description: CRITICAL flaws discovered in TrendMomentumService - CAGR bug, missing validation, zero tests
type: project
---

# Step 5.2 Trend Momentum Score — Critical Vulnerabilities

**Date**: 2026-03-26  
**Status**: CRITICAL FLAWS IDENTIFIED — BLOCK STEP 5.3

## Three CRITICAL Flaws

### CRITICAL-1: CAGR Exponent Bug (9x Error)
- **Location**: src/aievograph/domain/services/trend_momentum_service.py:83
- **Issue**: Uses `recent_years` parameter instead of actual data span
- **Impact**: 2 years of data with recent_years=5 → CAGR is 9x too low (0.53 vs 4.5)
- **Fix**: Use `len(sorted(yearly_counts))` instead of `recent_years` for exponent

### CRITICAL-2: No Negative Count Validation
- **Location**: _shannon_entropy (line 87-104), _adoption_velocity (line 107-139)
- **Issue**: No validation that counts must be >= 0
- **Impact**: Negative counts produce negative entropy (mathematically invalid)
- **Fix**: Validate all counts >= 0, skip methods with invalid data

### CRITICAL-3: Zero Unit Tests (TDD Violation)
- **Location**: Missing tests/test_trend_momentum_service.py
- **Issue**: No unit tests exist for metric functions or service
- **Impact**: CRIT-1 and CRIT-2 were never caught
- **Fix**: Create 30+ test cases covering all edge cases and contracts

## Four HIGH Severity Issues

1. **Type Validation Missing** (line 193-194): Repository might return string years, not int
2. **Weight Sum Not Validated** (line 185-186): Allows alpha+beta+gamma != 1.0
3. **Year Parameters Unvalidated** (line 181): Allows year_end=3000, negative year_start
4. **Repository Layer Unvalidated** (neo4j_method_trend_repository.py:53): Also doesn't validate

## Test Coverage Status

- Current: 320 tests pass, 9 skipped — NONE for TrendMomentumService
- Adversarial tests created: 5 tests, 3 prove CRITICAL flaws
- All vulnerabilities are real and exploitable

## Recommendation

BLOCK Step 5.3 development until:
1. CAGR exponent is fixed
2. Negative count validation added
3. tests/test_trend_momentum_service.py created with 30+ tests
4. Weight/year parameter validation added

Estimated effort: 4-6 hours
Risk if unfixed: HIGH (systematic misranking, data corruption)
