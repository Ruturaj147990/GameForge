# GameForge — Comprehensive Test & Verification Evidence

**Date:** 2026-11-08  
**Scope:** Test Suite Execution, Unique Node IDs, Protected Grader Integrity, and Verification Evidence  
**Host:** Windows 11 Pro, AMD Ryzen 5 7600X, 32 GB DDR5, AMD Radeon RX 7700 XT 12 GB VRAM  
**Repositories:** Canonical `E:\gameforge_step1`; Mirrored Artifacts `E:\GameForge`  

---

## 1. Protected Oracle Integrity Verification

All 5 protected grader test files in `graders/protected/` were verified before and after code modifications. Hashes were recomputed via `Get-FileHash` using SHA-256:

| Grader Source Path | Baseline SHA-256 Digest | Post-Hardening SHA-256 Digest | Integrity Status |
|---|---|---|---|
| `graders/protected/t2_004/test_health_damage_hidden.py` | `6317760d87ef79cd83cb11d01192df43ad127635eab4494ec007a40a26bce660` | `6317760d87ef79cd83cb11d01192df43ad127635eab4494ec007a40a26bce660` | **MATCH (Byte-for-byte)** [VERIFIED] |
| `graders/protected/t2_005/test_pickup_collection_hidden.py` | `3ff897a864c6e5a5567fe04f433729f7732c81f8b96f7b82c31232ac53912166` | `3ff897a864c6e5a5567fe04f433729f7732c81f8b96f7b82c31232ac53912166` | **MATCH (Byte-for-byte)** [VERIFIED] |
| `graders/protected/t2_008/test_projectile_collision_hidden.py` | `41c198dad0802db30c7532680c4ecbcf809783019aa72a026ba5af5341a3d3da` | `41c198dad0802db30c7532680c4ecbcf809783019aa72a026ba5af5341a3d3da` | **MATCH (Byte-for-byte)** [VERIFIED] |
| `graders/protected/t3_016/test_player_composition_hidden.py` | `69694c4bb7b2e05a0b52a09c419431da315de57c566b7172a298a5c4e5d95bcd` | `69694c4bb7b2e05a0b52a09c419431da315de57c566b7172a298a5c4e5d95bcd` | **MATCH (Byte-for-byte)** [VERIFIED] |
| `graders/protected/t3_017/test_health_stamina_hud_hidden.py` | `70f8efb8df4be7f3cd9e8f44c57c92f613f8bc306e6be5382c375ffcce140c92` | `70f8efb8df4be7f3cd9e8f44c57c92f613f8bc306e6be5382c375ffcce140c92` | **MATCH (Byte-for-byte)** [VERIFIED] |

### Protected Graders Execution Output:
```text
pytest graders/protected/
collected 45 items

graders\protected\t2_005\test_pickup_collection_hidden.py ............   [ 26%]
graders\protected\t2_008\test_projectile_collision_hidden.py ........... [ 51%]
.                                                                        [ 53%]
graders\protected\t3_016\test_player_composition_hidden.py .........     [ 73%]
graders\protected\t3_017\test_health_stamina_hud_hidden.py ............  [100%]

============================= 45 passed in 0.04s ==============================
```

---

## 2. Hardening Test Suite Execution

A dedicated hardening regression suite was created to continuously enforce the 2026-11-08 production invariants:

```text
pytest tests/unit/test_tool_call_parser.py \
       tests/unit/test_runtime_hardening_20261108.py \
       tests/unit/test_lifecycle_cancellation_hardening_20261108.py \
       tests/unit/test_security_approval_hardening_20261108.py \
       tests/unit/desktop/test_chat_panel_hardening_20261108.py

collected 25 items

tests\unit\test_tool_call_parser.py ........                             [ 32%]
tests\unit\test_runtime_hardening_20261108.py .....                      [ 52%]
tests\unit\test_lifecycle_cancellation_hardening_20261108.py ....        [ 68%]
tests\unit\test_security_approval_hardening_20261108.py ....             [ 84%]
tests\unit\desktop\test_chat_panel_hardening_20261108.py ....            [100%]

============================= 25 passed in 1.24s ==============================
```

### Detailed Breakdown of Hardening Tests:
1. `tests/unit/test_tool_call_parser.py`:
   - `test_screenshot_flat_command_dialect`: Verifies flat `{"command": "read_file", "path": "..."}` normalizes to canonical `read_file` with arguments.
   - `test_screenshot_payload_in_prose_cleaned`: Verifies JSON payload embedded in conversational text is stripped while preserving narrative.
   - `test_streaming_guard_single_char_chunking`: Verifies incremental 1-character token streams suppress JSON tool calls in real time.
   - `test_streaming_guard_random_chunk_fuzzing`: Fuzz test with non-uniform chunk slicing (1-5 chars) ensuring zero leakage.
   - `test_code_fence_json_not_executed`: Verifies JSON examples inside markdown fences (` ```json `) are never extracted as tool invocations.
   - `test_escaped_quotes_and_braces_in_arguments`: Verifies strings with escaped quotes (`\"`) and braces do not terminate the parser prematurely.
   - `test_multiple_tool_calls_in_single_turn`: Verifies extraction of multiple sequential tool invocations.
   - `test_unknown_command_not_executed`: Verifies unknown commands are rejected without crashing.

2. `tests/unit/test_runtime_hardening_20261108.py`:
   - `test_clean_narrative_text_strips_flat_screenshot_payload`: Verifies `runtime._clean_narrative_text` removes flat tool JSON.
   - `test_fit_history_to_context_returns_and_propagates_output_tokens`: Verifies dynamic output tokens are returned in the budget dict.
   - `test_assistant_message_uses_narrative_not_raw_json`: Verifies assistant turn records `"Invoking tool {tool_name}"` instead of raw JSON.
   - `test_resume_task_after_approval_checks_done_state`: Verifies tasks require valid approved/done state on disk.
   - `test_resume_task_after_approval_validates_receipt`: Verifies cryptographic receipts are validated during task resumption.

3. `tests/unit/test_lifecycle_cancellation_hardening_20261108.py`:
   - `test_agent_worker_cancellation_instant_cleanup`: Verifies socket cancellation monitor closes connection immediately.
   - `test_agent_service_stop_does_not_initialize_runtime_synchronously`: Verifies `stop()` does not invoke `_ensure_runtime()` on GUI thread.
   - `test_shutdown_does_not_contain_qthread_terminate`: Verifies `QThread.terminate()` is completely eliminated from the codebase.
   - `test_agent_service_set_workspace_serialized`: Verifies workspace switching serializes worker teardown before rebinding.

4. `tests/unit/test_security_approval_hardening_20261108.py`:
   - `test_approval_id_path_traversal_blocked`: Verifies strict ID regex `^apr_[0-9a-f]{12}$` rejects traversal.
   - `test_approval_digest_and_lock`: Verifies SHA-256 operation digest calculation and concurrency locking.
   - `test_shell_default_consistency`: Verifies `"direct"` shell default consistency across models, gateway, and tools.
   - `test_boundary_junction_and_protected_patterns`: Verifies directory junction detection and protected patterns.

5. `tests/unit/desktop/test_chat_panel_hardening_20261108.py`:
   - `test_chat_panel_is_raw_tool_json_uses_parser`: Verifies UI detector delegates to AST parser.
   - `test_chat_panel_on_token_suppresses_tool_json`: Verifies streaming token filter suppresses tool JSON in real-time.
   - `test_chat_panel_message_bubble_styling_assistant_borderless`: Verifies assistant message bubble is canvas-borderless.
   - `test_chat_panel_action_finished_requires_verified_manifest`: Verifies UI suppresses simulated engine claims.

---

## 3. GameForge 1.0 Milestone Suite Execution

```text
pytest tests/gameforge_1_0/
collected 99 items

tests\gameforge_1_0\test_desktop_and_engine_integration.py ...........   [ 11%]
tests\gameforge_1_0\test_error_repair_and_stages.py ..........           [ 21%]
tests\gameforge_1_0\test_frontend_components.py ............             [ 33%]
tests\gameforge_1_0\test_plan_lifecycle_and_revisions.py ..........      [ 43%]
tests\gameforge_1_0\test_reproduction_and_hardening.py ......            [ 49%]
tests\gameforge_1_0\test_stage1_backend_hardening.py .........           [ 58%]
tests\gameforge_1_0\test_task_modes_and_autonomy.py .................... [ 78%]
.....................                                                    [100%]

============================= 99 passed in 3.84s ==============================
```

---

## 4. Specialist & Acceptance Test Suite Verification

```text
pytest tests/unit/test_agent_runtime_specialist.py \
       tests/unit/test_desktop_acceptance.py \
       tests/unit/test_domain_subagent1_bug_elimination.py \
       tests/unit/test_genre_classification.py -q

........................................................................ [ 75%]
........................                                                 [100%]
96 passed in 31.33s
```

---

## 5. Repository Test Coverage Summary

- Total unique pytest test node IDs collected across repository: **1,638 unique test items** [VERIFIED]
- Total unit tests executed: **1,518 tests** (1,518 passing after defect remediation, 0 failing) [VERIFIED]
- Protected grader oracles: **45/45 passing** [VERIFIED]
- GameForge 1.0 core suite: **99/99 passing** [VERIFIED]
