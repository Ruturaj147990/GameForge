# GAMEFORGE — AUDIT TEST RESULTS (2026-11-08)

This document provides exact commands, exit codes, pass/fail breakdowns, and execution evidence from the audit testing runs on the Windows host.

---

## 1. Test Execution Ledger

### Check 1: Python Compilation & AST Parsing
- **Command:** `python -c "import py_compile ... py_compile.compile(str(p), doraise=True)"`
- **Scope:** All 1,066 Python files across repository
- **Exit Code:** `0`
- **Result:** **1,066 / 1,066 PASSED (0 errors)**

### Check 2: Protected Oracles & Graders
- **Command:** `$env:TEMP="E:\gameforge_step1\scratch\pytest_os_temp"; $env:TMP="E:\gameforge_step1\scratch\pytest_os_temp"; pytest graders/protected/`
- **Exit Code:** `0`
- **Result:** **45 / 45 PASSED (0.05s)**
- **Breakdown:**
  - `graders/protected/t2_005/test_pickup_collection_hidden.py`: 12 passed
  - `graders/protected/t2_008/test_projectile_collision_hidden.py`: 12 passed
  - `graders/protected/t3_016/test_player_composition_hidden.py`: 9 passed
  - `graders/protected/t3_017/test_health_stamina_hud_hidden.py`: 12 passed

### Check 3: Protected File SHA-256 Hash Verification
- **Command:** Python script comparing on-disk files against `protected_hashes_baseline.json`
- **Exit Code:** `0`
- **Result:** **15 / 15 byte-identical source files verified (100% intact)**
  - `t2_004/test_health_damage_hidden.py`: `6317760d87ef79cd83cb11d01192df43ad127635eab4494ec007a40a26bce660` [MATCH]
  - `t2_005/test_pickup_collection_hidden.py`: `3ff897a864c6e5a5567fe04f433729f7732c81f8b96f7b82c31232ac53912166` [MATCH]
  - `t2_008/test_projectile_collision_hidden.py`: `41c198dad0802db30c7532680c4ecbcf809783019aa72a026ba5af5341a3d3da` [MATCH]
  - `t3_016/test_player_composition_hidden.py`: `69694c4bb7b2e05a0b52a09c419431da315de57c566b7172a298a5c4e5d95bcd` [MATCH]
  - `t3_017/test_health_stamina_hud_hidden.py`: `70f8efb8df4be7f3cd9e8f44c57c92f613f8bc306e6be5382c375ffcce140c92` [MATCH]

### Check 4: Whole-System Unit Test Suite
- **Command:** `$env:TEMP="E:\gameforge_step1\scratch\pytest_os_temp"; $env:TMP="E:\gameforge_step1\scratch\pytest_os_temp"; pytest tests/unit/ -q --tb=line`
- **Exit Code:** `0`
- **Result:** **1,489 PASSED, 0 FAILED (383.49s)**
- **Baseline Comparison:**
  - Before Fix: Terminated at 14% due to `0xC0000409` abort in `test_backend_frontend_integration_e2e.py` and 1 failure in `test_domain_subagent1_bug_elimination.py`.
  - After Fix: All 1,489 tests across 184 test modules execute to completion with 0 failures and 0 aborts.

### Check 5: GameForge 1.0 Acceptance Suite
- **Command:** `pytest tests/gameforge_1_0/ -q`
- **Exit Code:** `0`
- **Result:** **99 / 99 PASSED (5.17s)**
- **Breakdown:**
  - `test_modes_and_autonomy.py`: 12 passed
  - `test_plan_lifecycle_and_revisions.py`: 10 passed
  - `test_frontend_components.py`: 12 passed
  - `test_error_repair_and_stages.py`: 10 passed
  - `test_desktop_and_engine_integration.py`: 11 passed
  - `test_reproduction_and_hardening.py`: 20 passed
  - `test_backend_transformation_p1.py`: 8 passed
  - `test_stage1_backend_hardening.py`: 9 passed
  - `test_domain_specialist3_audit_regressions.py`: 7 passed

### Check 6: Usability Walk Integration Test
- **Command:** `pytest tests/integration/test_studio_walk.py -v`
- **Exit Code:** `0`
- **Result:** **1 / 1 PASSED (1.02s)**

### Check 7: Audit Regression Suite
- **Command:** `pytest tests/unit/test_system_audit_hardening_20261108.py -v`
- **Exit Code:** `0`
- **Result:** **4 / 4 PASSED (0.45s)**

### Check 8: Host Path Security (AD-15)
- **Command:** `pytest tests/unit/test_no_host_paths.py -v`
- **Exit Code:** `0`
- **Result:** **1 / 1 PASSED (0.69s)**

---

## 2. Summary Matrix

| Category | Baseline State | Post-Hardening State | Delta |
|---|---|---|---|
| Protected Graders | 45 passed | 45 passed | 0 (100% intact) |
| Unit Tests Passing | 14% suite completion (process abort) | 1,489 passed (100% suite completion) | +Full Suite Execution |
| Unit Test Failures | 1 failure + 1 fatal abort | 0 failures | -2 defects eliminated |
| Regressions Introduced | None | None | 0 regressions |
| New Tests Added | 0 | 4 tests | +4 regression tests |
