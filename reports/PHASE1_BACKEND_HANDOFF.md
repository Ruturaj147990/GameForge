# GameForge 1.0 — Phase 1 Backend Transformation Handoff Package
**Authoritative Architectural Specification, Integration Contracts, and Handover Protocol**
**Date:** 2026-11-06 | **Phase 1 Completion State:** [VERIFIED] | **Target Audience:** Phase 2 Frontend Agent, Phase 2 Test-Creation Agent, Main Coordinator

---

## 1. Executive Summary & Transformation Rationale

Phase 1 completes the comprehensive backend overhaul of GameForge 1.0 under the Master Transformation Directive. GameForge has transitioned from a rigid, detour-heavy toolchain into a genuinely autonomous software-engineering and game-development IDE with capabilities, interaction patterns, and intelligence execution on par with Google Antigravity and Claude Code.

### Key Architectural Resolutions:
1. **Universal Assistant Entry Point:** Eliminated the legacy hardcoded detour (`is_create or is_change` -> `open_design` card -> Home Design Flow) in `AgentRuntime`. The assistant now directly understands, plans, and executes engineering tasks, code modifications, and full 11-stage Unreal Engine pipelines within the primary conversation.
2. **Two Independent User Selectable Controls:**
   - **Task Approach (`TaskMode`):** `Planning` (deliberative planning with structured technical `PlanArtifact` in chat, multi-turn revisions, and `Proceed` confirmation) vs `Fast` (immediate autonomous execution with internal reasoning and verification).
   - **Autonomy Profile (`AutonomyProfile`):** `Manual` (explicit approval required for file edits, commands, builds), `Auto-Edit` (automatic project inspection and workspace file edits with rollback journal; approval required for commands and builds), and `Agentic` (fully autonomous safe edits, allowlisted commands, tests, Unreal ops; approval gated only for destructive/high-risk actions).
3. **Deterministic Error Repair Engine (`RepairEngine`):** Strictly enforces a 5-attempt limit per root-cause, automatically halts after 2 consecutive attempts without diagnostic progress, avoids cyclic edits, and selectively invalidates downstream DAG stages on failure without invalidating upstream completed work.
4. **Selective Pipeline Resumption in `ForgeExecutor`:** Upstream stages (1–8) remain valid when a downstream stage (such as stage 9 `scenarios`) is repaired and retried, eliminating redundant compilation or packaging.
5. **Atomic File Editing & Disk Read-Back:** Added `write_file`, `verify_disk`, and atomic multi-file baseline transactions with `DiffStore` rollback journals.

---

## 2. Core Backend Architecture & State Machine

### 2.1 Authoritative Task Lifecycle State Machine (`TaskLifecycleStatus`)
The backend state machine governs every task from user submission through completion:

```
[CREATED] ──► [UNDERSTANDING] ──► [PLANNING] ──► [AWAITING_PLAN_APPROVAL] ──► [RUNNING]
                     │                 │                                          │
                     ▼                 ▼                                          ├──► [WAITING_TOOL]
               [COMPLETED]*        [RUNNING] (Fast Mode)                          ├──► [AWAITING_PERMISSION]
                                                                                  ├──► [REPAIRING] ◄──┐
                                                                                  ├──► [VERIFYING] ────┘
                                                                                  ├──► [COMPLETED]
                                                                                  ├──► [FAILED]
                                                                                  └──► [BLOCKED]
```
* Informational queries (Q&A) complete directly from `UNDERSTANDING`.

### 2.2 Task Lifecycle States
1. `CREATED`: Initial task state on receipt of user prompt.
2. `UNDERSTANDING`: Intent classification, conversational routing, and acceptance predicate extraction.
3. `INVESTIGATING`: Workspace exploration, codebase indexing, and symbol discovery.
4. `PLANNING`: Formulating structured execution steps (`PlanArtifact`).
5. `AWAITING_PLAN_APPROVAL`: Plan displayed in chat; awaiting user revisions or `Proceed`.
6. `QUEUED`: Approved task waiting for execution thread/engine lock.
7. `RUNNING`: Actively reasoning, generating code, or executing tools.
8. `WAITING_TOOL`: Blocked awaiting asynchronous tool execution output.
9. `AWAITING_PERMISSION`: Paused awaiting explicit user approval for a gated tool/diff.
10. `REPAIRING`: Proactively diagnosing a tool, compiler, or scenario failure.
11. `VERIFYING`: Evaluating machine-checkable acceptance predicates over disk/engine state.
12. `COMPLETED`: All acceptance criteria satisfied with verified evidence.
13. `FAILED`: Terminal failure after exhausting repair attempts or encountering unrecoverable error.
14. `BLOCKED`: Dependency missing, repeated action cycle, or user rejection.
15. `CANCELLED`: Cooperatively cancelled by developer.

---

## 3. Task Modes and Autonomy Profiles Specification

### 3.1 Task Modes (`TaskMode`)
- **`planning` (`TaskMode.PLANNING`):**
  - Synthesizes a structured `PlanArtifact` rendered directly in chat.
  - Multi-turn revisions: User can submit refinement prompts (e.g., "Add double jump", "Use Blueprint instead of C++"). The plan increments version (1 -> 2 -> 3) while preserving history.
  - Confirmation: Single click on `Proceed` (or typing "proceed", "go ahead", "apply") triggers execution.
- **`fast` (`TaskMode.FAST`):**
  - Bypasses chat plan review.
  - Executes immediately through the autonomous tool loop with real-time status and token streaming.

### 3.2 Autonomy Profiles (`AutonomyProfile`)
Enforced at the backend gateway level (`src/gameforge_ide/backend/tools/gateway.py`):

| Operation Class | `Manual` Profile | `Auto-Edit` Profile | `Agentic` Profile |
| :--- | :--- | :--- | :--- |
| **Read-Only Inspection** (`read_file`, `list_dir`, `verify_disk`, `search_code`, `git_status`) | Auto-proceeds | Auto-proceeds | Auto-proceeds |
| **Workspace File Mutations** (`write_file`, `apply_edit`, `rollback_edit`) | Pauses with `WAITING_APPROVAL` | **Auto-applies with rollback tracking** | **Auto-applies with rollback tracking** |
| **Safe Dev Commands & Tests** (`pytest`, `git diff`, `unreal_run_tests`, `unreal_build`) | Pauses with `WAITING_APPROVAL` | Pauses with `WAITING_APPROVAL` | **Auto-proceeds to completion** |
| **Destructive / High-Risk Ops** (arbitrary shell, file deletions, packaging, raw editor ops) | Pauses with `WAITING_APPROVAL` | Pauses with `WAITING_APPROVAL` | Pauses with `WAITING_APPROVAL` |

---

## 4. Plan Artifact Data Contract (`PlanArtifact`)

Exported in `src/gameforge_ide/backend/models/plan_artifact.py`:

```json
{
  "plan_id": "plan_7f3a91b2",
  "session_id": "sess_01234567",
  "version": 1,
  "goal": "Build Top-Down Roguelike Character Controller",
  "summary": "Implement enhanced input bindings, character movement component, and camera rig.",
  "implementation_method": "direct_code_edit",
  "steps": [
    {
      "step_id": "step_1",
      "title": "Inspect Existing Character Hierarchy",
      "description": "Locate base ACharacter class and verify existing EnhancedInput setup",
      "target_files": ["Source/Game/BaseCharacter.h"],
      "tools": ["search_code", "read_file"],
      "verification": "Identify existing component pointers and includes",
      "status": "pending"
    },
    {
      "step_id": "step_2",
      "title": "Implement Dash Movement Logic",
      "description": "Add Dash() function and cooldown timer in CharacterController.cpp",
      "target_files": ["Source/Game/CharacterController.cpp"],
      "tools": ["propose_edit", "apply_edit"],
      "verification": "Diff applied and verified on disk",
      "status": "pending"
    }
  ],
  "status": "awaiting_approval",
  "proceed_confirmed": false,
  "revisions": []
}
```

---

## 5. File Editing & Rollback System (`EditTools` & `ToolGateway`)

### 5.1 Tool Operations:
- **`propose_edit(subpath, target_content, replacement_content)`**: Computes unified diff, checks syntax boundaries, stores in `DiffStore`, returns `diff_id`. In `AUTO_EDIT` and `AGENTIC` profiles, the runtime automatically executes `apply_edit`. In `MANUAL` profile, it pauses with `WAITING_APPROVAL`.
- **`write_file(subpath, content)`**: Atomically writes or overwrites file inside workspace, recording pre-hash and post-hash with full rollback journal.
- **`verify_disk(subpath, expected_fragment)`**: Verifies file existence and disk content independently of memory caches.
- **`rollback_edit(diff_id)`**: Reverts single diff to pre-edit baseline.
- **`rollback_batch(diff_ids)`**: Reverts multi-file edits in reverse order.
- **`begin_transaction(files)`**: Captures SHA-256 baselines across multiple files before multi-file operations.

---

## 6. Error Repair Loop & 11 Forge Pipeline Stages

### 6.1 Repair Engine Policy (`RepairEngine`):
- Max **5 attempts per unique root cause** (`cause_id`).
- Stops immediately if **2 consecutive attempts make zero diagnostic progress**.
- Diff hashes per cause are tracked; exact duplicate proposed diffs are rejected as cyclic.

### 6.2 11 Forge Pipeline Stages & Invalidation Rules:
The canonical 11 stages in sequential order:
1. `design` (StepKind.DESIGN) — Generates GDS specification.
2. `scaffold` (StepKind.SCAFFOLD) — Creates project folder, `.uproject`, and build rules.
3. `build_editor` (StepKind.BUILD) — Compiles C++ editor binaries.
4. `content` (StepKind.CONTENT) — Generates materials, meshes, audio, VFX.
5. `assemble_level_1` (StepKind.ASSEMBLE) — Places actors and builds scene.
6. `scenario_gen` (StepKind.DESIGN) — Creates QA playtest specifications.
7. `automation` (StepKind.AUTOMATION) — Runs engine automation tests.
8. `package` (StepKind.PACKAGE) — Cooks and packages standalone game executable.
9. `scenarios` (StepKind.SCENARIO) — Executes automated QA playtest scenarios.
10. `review` (StepKind.REVIEW) — Validates acceptance criteria and evidence logs.
11. `report` (StepKind.REPORT) — Generates final run report and evidence bundle.

**Downstream Invalidation:**
`ForgeExecutor.invalidate_stage_and_downstream(state, stage_id)` invalidates the specified stage and all downstream stages in the DAG, resetting them to `StepStatus.PENDING`.
**All upstream completed stages remain `StepStatus.DONE`** and are automatically skipped on `ForgeExecutor.resume()`.

---

## 7. Frontend Integration Contract (For Phase 2 Frontend Agent)

### 7.1 Single Primary Assistant View:
The frontend must present a single universal assistant interface in the primary chat/workspace.
- **Retire Separate Design and Build Pages:** The separate Design and Build pages are no longer primary navigation entry points. All requests (building games, editing code, running tests, fixing bugs) flow directly through the assistant chat.
- **Remove `open_design` Card Detour:** The UI must never force prompt redirection or double-submission.

### 7.2 Two Independent Header / Session Selectors:
1. **Task Approach Selector:**
   - Options: `Planning` (default) vs `Fast`.
   - Bound to `session.task_mode` via `SessionManager.set_session_mode(session_id, task_mode=...)`.
2. **Autonomy Profile Selector:**
   - Options: `Manual`, `Auto-Edit`, `Agentic` (default).
   - Bound to `session.autonomy_profile` via `SessionManager.set_session_mode(session_id, autonomy_profile=...)`.

### 7.3 Streaming Event Contract (`AgentEvent` Types):
The WebSocket/IPC stream emits typed events:
- `status`: Lifecycle updates (`PLANNING`, `RUNNING`, `EXECUTING_TOOL`, `REPAIRING`, `VERIFYING`, `WAITING_APPROVAL`).
- `token`: Streaming narrative/explanation text tokens.
- `plan`: Structured `PlanArtifact` payload (render as an interactive card in chat with `Proceed` button and step checklist).
- `tool_call`: Dispatched tool and arguments.
- `tool_result`: Output observation and status.
- `file_changed`: Disk modification event with file path and diff ID.
- `diff_pending`: Proposed diff waiting for manual approval (in `MANUAL` profile).
- `error`: Diagnostic error notification.
- `done`: Task completion notification.

---

## 8. Acceptance Test Specification (For Phase 2 Test-Creation Agent)

The Phase 2 Test-Creation Agent must construct an independent, difficult, production-grade test suite. The Test-Creation Agent **must author tests only and must NOT execute them**.

### Required Test Dimensions:
1. **Frontend / UI Component Tests:**
   - Verification of Task Approach (`Planning`/`Fast`) and Autonomy (`Manual`/`Auto-Edit`/`Agentic`) UI selectors.
   - Interactive `PlanArtifact` card widget rendering, step progress markers, and `Proceed` button dispatch.
   - Elimination of `open_design` redirection cards.
2. **Autonomy Profile Enforcement Tests:**
   - Strict gating: `MANUAL` blocks edits and commands.
   - Safe flow: `AUTO_EDIT` auto-applies workspace edits but gates external commands.
   - Full agentic flow: `AGENTIC` auto-executes allowlisted dev tools (`pytest`, safe Unreal builds/tests) without user prompting.
3. **Multi-Turn Plan Revision & Execution Tests:**
   - Plan generation -> revision -> version increment -> proceed confirmation -> execution.
4. **Error Recovery & Stage Resumption Tests:**
   - Stage 9 (`scenarios`) failure reproduction and selective downstream invalidation.
   - Preservation of stages 1..8 on pipeline resume.
   - Halting after 5 attempts or 2 no-progress iterations.
5. **Real Engine & Desktop GUI Verification:**
   - Real PySide6 window launch and teardown (confirming `win.confirm_on_close = False`).
   - Unreal Engine 5.7.4 live bridge and command allowlist verification.

---

## 9. Handover Completion Verification Gate
- **Protected Oracles:** 45/45 PASS (`python -m pytest graders/protected/ -q -p no:cacheprovider`).
- **Phase 1 Backend Suite:** 8/8 PASS (`python -m pytest tests/unit/test_backend_transformation_p1.py -v -p no:cacheprovider`).
- **Domain Regressions Suite:** 11/11 PASS (`python -m pytest tests/unit/test_domain_specialist3_audit_regressions.py -v -p no:cacheprovider`).
- **Zero Frontend Modifications in Phase 1:** All UI files preserved strictly for Phase 2.
- **Phase 1 Exit Criteria Satisfied:** Ready for Phase 2 activation.
