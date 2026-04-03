---
name: Step 6.4 Insight Panel Adversarial Audit Findings
description: 12 vulnerabilities found in Breakthrough Detection and Trend Momentum features - 3 Critical, 4 High, 5 Medium
type: project
---

# Step 6.4 Insight Panel Adversarial Audit — Complete Findings

**Date**: 2026-04-03  
**Components Tested**:
- Feature 2: Breakthrough Detection (frontend + backend)
- Feature 3: Trend Momentum Analysis (frontend + backend)

## Severity Breakdown
- **CRITICAL**: 3 bugs (NaN rendering, silent evolution failure, incomplete API contract)
- **HIGH**: 4 bugs (year validation, slider guard, score card NaN, ambiguous 404)
- **MEDIUM**: 5 bugs (all-zero bars, no response validation, empty inputs, data loss, empty tab)

## Critical Vulnerabilities

### C1: Unguarded NaN in Bar Chart (breakthrough-view.tsx:55)
- **Attack**: API returns NaN composite_score
- **Impact**: maxScore=NaN, bar dimensions=NaN, silent render failure
- **Fix**: Guard maxScore against NaN/Infinity before rendering

### C2: Silent Evolution Path Failure (trend.py:117)
- **Attack**: EvolutionPathService.extract() raises exception
- **Impact**: Frontend receives evolution_path=[], no error indication
- **Fix**: Return explicit error in response or raise HTTPException

### C3: Incomplete yearly_scores API Contract (trend.py:74-76)
- **Attack**: Any trend query returns yearly_scores=[{year: end_year, usage_count: 0}]
- **Impact**: Single stub element instead of full yearly breakdown
- **Fix**: Populate with actual yearly counts for window

## High Severity Vulnerabilities

### H1: No Year Bounds Validation (schemas)
- Allows start_year=1900, end_year=3000
- Validator only checks start_year <= end_year
- Fix: Add [1930, 2025] bounds

### H2: Year Slider Can Stay Stale (both views, onValueChange)
- Length check v.length >= 2 blocks setYearRange on single-value events
- Mid-drag may not update yearRange
- Fix: Remove length check or handle gracefully

### H3: NaN in Score Cards (trend-view.tsx:36-49)
- toFixed(NaN) produces "NaN" string in UI
- No isFinite guard in ScoreCard component
- Fix: Check isFinite(value) before formatting

### H4: Ambiguous 404 Error (trend.py:49-67)
- Unknown topic, known topic no data, search error all return 404
- Cannot distinguish failure modes
- Fix: Return distinct HTTP codes (404, 204, etc)

## Medium Severity Vulnerabilities

### M1: All-Zero Bar Chart (breakthrough-view.tsx:55-62)
- maxScore=0.01 if all scores zero
- All bars height=0, confusing UX
- Fix: Show "No breakthroughs detected" message

### M2: No API Response Validation (lib/api.ts:14-25)
- Unchecked cast: return res.json() as Promise<TRes>
- Runtime type mismatches go silent
- Fix: Use Zod runtime schema validation

### M3: Silent Empty Input (both views)
- if (!field.trim()) return; — no error shown
- User confusion
- Fix: Show "Please enter field" error

### M4: Repository Missing Paper Data Loss (breakthrough.py:84)
- Paper not in repo → title=paper_id, year=None
- Silent data loss not logged
- Fix: Log warning or return partial-failure flag

### M5: Empty Evolution Path Tab (graph-view-panel.tsx)
- evolution_path=[] renders empty with no message
- User confused about state
- Fix: Check length and display message

## Test Coverage

**Test File**: tests/test_step64_insight_panel_adversarial.py (9 tests)

**Tests Added**:
- BreakthroughRequest validation (empty field, zero top_k, year range)
- TrendRequest validation (empty methods, weight sum)
- Service edge cases (empty inputs, all zeros, single year)
- Response structure (nullable fields, empty arrays)

**All Tests Pass**: 9/9 ✓

## Architecture Compliance

- Clean Architecture: ✓ PASS (no layer violations)
- TDD Mandate: ✓ PARTIAL (Layer D tested, frontend components not)
- Port/Adapter: ✓ PASS (Layer D depends only on Layer A)

## How to Apply (Priority Order)

**Priority 1 (CRITICAL - Fix Before Release)**:
1. Add NaN guard in bar chart: `if (scores.filter(isFinite).length === 0) return <NoData />`
2. Return error on evolution path failure (not silent suppression)
3. Populate yearly_scores with actual data, not stub

**Priority 2 (HIGH - Fix Before 6.4 Complete)**:
4. Add year bounds [1930, 2025] to schemas
5. Fix slider onValueChange to handle single values
6. Add isFinite check in ScoreCard component
7. Return distinct error codes for missing topic vs no data

**Priority 3 (MEDIUM - Future Hardening)**:
8. Add "No breakthroughs detected" message for all-zero scores
9. Use Zod for API response validation
10. Show error message for empty input fields
11. Log warnings for missing repository data
12. Add "Evolution data unavailable" message

## Recurring Patterns Identified

**Pattern 1: Silent Error Suppression**
- Evolution path failure caught but not reported
- Causes user confusion (no data vs failed)
- Recommendation: Explicit error states in all async operations

**Pattern 2: Missing Input Validation**
- Year bounds unchecked
- Empty fields accepted
- Recommendation: Validate all user inputs before API call

**Pattern 3: NaN/Infinity Handling**
- Bar chart maxScore can become NaN
- Score cards don't guard against NaN
- Recommendation: Audit all division/formatting for edge cases

**Pattern 4: API Contract Violations**
- yearly_scores field semantics don't match implementation
- Recommendation: Add integration tests validating response schema matches frontend expectations

