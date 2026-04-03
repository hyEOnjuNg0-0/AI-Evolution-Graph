# Step 6.4 Insight Panel — Adversarial Security Audit

**Date**: 2026-04-03  
**Status**: CRITICAL VULNERABILITIES FOUND

## Critical Bugs Found

### 1. NaN in Bar Chart Rendering (CRITICAL)
**File**: frontend/components/breakthrough-view.tsx:55
**Issue**: maxScore = Math.max(...candidates.map(c => c.composite_score), 0.01)
- If all scores are NaN, maxScore becomes NaN
- SVG bars render with NaN dimensions
- Chart silently fails; no error message

**Fix**: Guard against NaN/Infinity before rendering

### 2. Silent Evolution Path Failure (CRITICAL)
**File**: src/aievograph/api/routers/trend.py:117
**Issue**: Exception suppressed with catch-all handler
- Backend fails extracting evolution path
- Frontend receives empty evolution_path array
- No indication to user that data is missing
- User cannot distinguish "no data" from "failed"

**Fix**: Return error in response or raise HTTPException

### 3. Incomplete yearly_scores API Contract (CRITICAL)
**File**: src/aievograph/api/routers/trend.py:74-76
**Issue**: yearly_scores always contains exactly 1 element with usage_count=0
- Schema promises list of yearly breakdown
- Backend returns only stub data
- Frontend cannot render per-year usage chart

**Fix**: Return actual yearly counts for analysis window

### 4. No Year Bounds Validation (HIGH)
**Files**: api/schemas/breakthrough.py:10-14, api/schemas/trend.py:9-13
**Issue**: Validator only checks start_year <= end_year
- No bounds check [1930, 2025]
- User can submit start_year=1900, end_year=3000
- Backend behavior undefined for invalid years

**Fix**: Add min/max bounds to validation

### 5. Year Slider Can Stay Stale (HIGH)
**Files**: breakthrough-view.tsx:293-296, trend-view.tsx:176-179
**Issue**: onValueChange checks v.length >= 2, setYearRange not called if false
- Mid-drag fires single value
- Array length = 1, guard fails
- Year range never updates on that drag event

**Fix**: Remove unnecessary length check or handle single value case

### 6. NaN in Trend Score Cards (HIGH)
**File**: trend-view.tsx:36-49
**Issue**: ScoreCard doesn't guard against NaN/Infinity
- toFixed(NaN) = "NaN"
- Renders "NaN" in UI
- No error boundary for invalid scores

**Fix**: Check isFinite(value) before formatting

### 7. Ambiguous 404 Error (HIGH)
**File**: api/routers/trend.py:49-67
**Issue**: Single 404 error for three different failure modes
- Unknown topic
- Known topic with no data
- Search function error
- User cannot tell which happened

**Fix**: Return distinct error codes/messages

### 8. All-Zero Scores Bar Chart (MEDIUM)
**File**: breakthrough-view.tsx:55-62
**Issue**: If all composite_scores=0, maxScore=0.01, all bars have height 0
- Chart renders blank
- Confusing to user (is chart loading? broken? empty?)

**Fix**: Show "No breakthroughs detected" instead of blank chart

### 9. No API Response Validation (MEDIUM)
**File**: frontend/lib/api.ts:14-25
**Issue**: return res.json() as Promise<TRes> is unchecked cast
- Runtime type mismatch goes silent
- Missing fields cause undefined access in components
- No schema validation

**Fix**: Use Zod or runtime type validation

### 10. Empty Input Field Accepted (MEDIUM)
**Files**: breakthrough-view.tsx:187, trend-view.tsx:72
**Issue**: if (!field.trim()) return; — no error shown
- User clicks "Detect" with empty field
- Form does nothing
- User confused (bug or feature?)

**Fix**: Show "Please enter a field" error message

### 11. Repository Missing Paper Data Loss (MEDIUM)
**File**: api/routers/breakthrough.py:84
**Issue**: Paper not found → title=paper_id, year=None
- Silent data loss
- User doesn't know title/year are missing

**Fix**: Log warning or return partial failure indicator

### 12. Empty Evolution Path Tab (MEDIUM)
**File**: graph-view-panel.tsx usage with trendResult
**Issue**: evolution_path=[] renders empty tab with no message
- No "Evolution data unavailable" message
- User confused about tab state

**Fix**: Check length and display appropriate message

