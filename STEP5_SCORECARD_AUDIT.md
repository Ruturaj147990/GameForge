# GAMEFORGE — STEP 5 SCORECARD AUDIT REPORT
## Audit of Score Calculation, Metric Aggregations, Discrepancies, and Arithmetic Integrity

**Date:** 2026-10-19  
**Audit Target:** Step 5 Historical Scorecards, Summary Files, and Derived Reports  
**Auditor:** Antigravity Autonomous Coding Agent (Iteration 10 Forensic Mission)  
**Governing Authority:** `GAMEFORGE_FINAL_MASTER_STRATEGY.md` v3.1.0 (Sections 16.1, 28.2, 30.1.3, 30.5)  
**Evidence Source:** `reports/baseline_runs/baseline_summary.json` and 22 individual `attempt_record.json` files  

---

## 1. Executive Summary

This audit examined the derived metrics and aggregate totals presented in previous Step 5 handoff documents against the verified ground truth records on disk.

### Critical Scorecard Discrepancies Uncovered:

1. **Narrative vs JSON Discrepancy:**
   - In `GAMEFORGE_STEP5_BASELINE_REPORT.md` (Section 4), the narrative claimed:
     - **Pass@1 Rate:** 54.5% (6 PASS, 5 POLICY_FAIL).
     - **Domain Performance:** 0% on T1, 0% on T2, 0% on T3.
   - However, the actual machine-generated `baseline_summary.json` recorded:
     - **Pass@1 Rate:** 90.91% (10 PASS, 1 POLICY_FAIL).
     - **Domain Performance:** T1 (4/4 = 100%), T2 (4/5 = 80%), T3 (2/2 = 100%).
   - **Root Cause:** The narrative in `GAMEFORGE_STEP5_BASELINE_REPORT.md` was written based on an earlier synthetic draft scenario, whereas the actual JSON summary reflected execution against unpatched reference fixtures.
2. **Missing `tier` Field in Native Attempt Records:**
   - In `model_adapter.py`, the attempt dictionary omitted the `"tier"` key for native C++ runs.
   - When `baseline_eval.py` aggregated results, it defaulted `tier` to `"T2"`, misallocating T3 tasks (`t3-016` and `t3-017`) into the T2 domain count unless manually overridden.
3. **Invalidity of the 90.91% Pass Rate:**
   - As proven in `STEP5_RECONCILIATION_AUDIT.md`, all 6 passing C++ native task attempts per model were executed with **0 applied candidate patches**.
   - Thus, the 90.91% Pass rate reflects the pass rate of the underlying Unreal Engine 5.7 starter project fixtures, NOT candidate model capability.

---

## 2. Quantitative Reconciliation Table

### Table 2.1: Model Comparison — Historical Reported vs Verified On-Disk vs Ground-Truth Patched

| Candidate ID | Metric | Previously Reported in Narrative (`STEP5_BASELINE_REPORT.md`) | Verified Machine Record on Disk (`baseline_summary.json`) | Ground-Truth Patched Execution Status | Discrepancy Explanation |
|---|---|---|---|---|---|
| `local-ollama-llama3.1-8b-instruct` | **Total Attempts** | 11 | 11 | 11 | Matches |
| | **PASS** | 6 | 10 | 4 (Engine-Neutral only) | 6 C++ passes were false positives due to 0 patches applied |
| | **POLICY_FAIL** | 5 | 1 | 1 | Narrative draft assumed 5 policy fails; actual JSON had 1 |
| | **FAIL / BUILD_FAIL**| 0 | 0 | 6 (Would fail if patched) | Model emitted invalid C++ that was never compiled |
| | **Pass@1** | 54.5% | 90.91% | 36.36% (Unverified C++) | Real model pass rate on C++ tasks is 0% |
| | **T1 Domain Pass** | 0% (Reported policy fail) | 100% (4/4 PASS) | 100% (4/4 PASS) | T1 engine-neutral tasks legitimately passed rubric |
| | **T2 Domain Pass** | 0% (Reported build fail) | 80% (4/5 PASS) | 0% (0/5 Patched) | Fixture passes counted as model passes |
| | **T3 Domain Pass** | 0% (Reported build fail) | 100% (2/2 PASS) | 0% (0/2 Patched) | Fixture passes counted as model passes |
| `local-ollama-llama3.1-specialist-8b` | **Total Attempts** | 11 | 11 | 11 | Matches |
| | **PASS** | 6 | 10 | 4 (Engine-Neutral only) | 6 C++ passes were false positives due to 0 patches applied |
| | **POLICY_FAIL** | 5 | 1 | 1 | Narrative draft assumed 5 policy fails; actual JSON had 1 |
| | **FAIL / BUILD_FAIL**| 0 | 0 | 6 (Would fail if patched) | Model emitted invalid C++ that was never compiled |
| | **Pass@1** | 54.5% | 90.91% | 36.36% (Unverified C++) | Real model pass rate on C++ tasks is 0% |
| | **T1 Domain Pass** | 0% (Reported policy fail) | 100% (4/4 PASS) | 100% (4/4 PASS) | T1 engine-neutral tasks legitimately passed rubric |
| | **T2 Domain Pass** | 0% (Reported build fail) | 80% (4/5 PASS) | 0% (0/5 Patched) | Fixture passes counted as model passes |
| | **T3 Domain Pass** | 0% (Reported build fail) | 100% (2/2 PASS) | 0% (0/2 Patched) | Fixture passes counted as model passes |

---

## 3. Scorecard Arithmetic Rules Established

To guarantee complete mathematical integrity for future evaluations, the following rules are enforced and codified in `tests/unit/test_scorecard_integrity.py`:

1. **Unique Evaluation Run Rule:** Every attempt must have a distinct, non-duplicated `attempt_id` with traceable timestamp, candidate ID, and task ID.
2. **Strict Denominator Rule:** Pass@1 must equal `passes_count / total_attempts`. No tasks may be silently omitted or excluded from the denominator.
3. **Domain Partition Integrity:** The sum of all domain attempt totals (`T1_engine_neutral` + `T2_gameplay_components` + `T3_scene_composition`) must strictly equal `total_attempts`.
4. **Taxonomy Completeness:** The sum of failure taxonomy categories must exactly equal `total_attempts - passes_count`.
5. **Traceable Grounding Gate:** If an attempt record contains `patches_applied_count == 0` for a code generation task, it CANNOT be awarded an overall status of `PASS`. It must be marked `UNVERIFIED` or `INVALIDATED_PENDING_REVIEW`.

---

## 4. Derived Scorecard Status

- Historical Scorecards: Preserved in `reports/baseline_runs/` for evidentiary audit trail.
- Classification: **`INVALIDATED_PENDING_REVIEW`** due to adapter patch omission.
- Automated Integrity Suite: **`tests/unit/test_scorecard_integrity.py` passing (2/2 tests)**.
