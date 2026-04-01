---
name: Phase 6 Step 6.2 Security & Contract Audit
description: Critical & High severity vulnerabilities in FastAPI Layer E Step 6.2 (Query Panel) — Year range reversal, null handling, missing validation
type: project
---

## Summary
Phase 6 Step 6.2 has NO existing tests for the FastAPI Layer (Layer E). Critical findings:

**Architecture**: Year range validation missing at schema/endpoint boundary between presentation and domain layers.

**Data Flow Contract Bugs**:
- Null year values silently coerced to 0, potentially bypassing filters
- Reversed year ranges (start > end) accepted without error
- LineageRequest/BreakthroughRequest/TrendRequest missing explicit year validation

**Frontend-Backend Contract Mismatches**:
- Year slider missing explicit step property (inconsistent with Top K slider)
- No frontend-side validation of year range reversal

Audit completed 2026-04-01.
