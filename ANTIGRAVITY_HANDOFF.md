# GameForge 1.0 — Master Transformation Handover Protocol

You are operating under the **GameForge 1.0 Master Transformation Directive**.
Claude's historical architecture and documentation are reference records, not unquestionable sources of truth. The actual verified repository, filesystem, and Unreal Engine 5.7.4 toolchain take precedence.

### Phase Execution Rules:
- **Phase 1 (Complete Backend Overhaul):** COMPLETED. Exactly 1 agent (Main Agent). All backend transformations verified.
- **Phase 2 (Frontend Overhaul & Test-Suite Creation):** COMPLETED. Exactly 3 agents (Main Coordinator, Frontend Specialist, Test-Creation Specialist). Delivered interactive PlanCard, Autonomy & Approach selectors, and independent test suite.
- **Phase 3 (Main Agent Executes Test Suite):** COMPLETED. Exactly 1 agent (Main Agent). Executed suite, resolved integration defects, 84/84 tests PASS.
- **Post-Transformation Audit & Hardening:** COMPLETED. Exactly 1 agent (Principal Architect / Auditor). Eliminated false capability refusals, prevented code-dump chat substitution via atomic file tools, eliminated retired Design/Build interfaces and redundant options, verified Tests A–E in `test_reproduction_and_hardening.py` (90/90 tests PASS in `tests/gameforge_1_0/`), 45/45 protected oracles PASS.

### Authoritative Reference Documents:
1. `context.md` — Primary source of truth.
2. `reports/PHASE1_BACKEND_HANDOFF.md` — Authoritative backend integration contracts, state machine, event streams, and tool schemas.
3. `DECISION_LOG.csv` — Architecture decision history (D-001 through D-066).
4. `docs/00_STATUS.md` — Current milestone status.

### Non-Negotiable Hard Constraints:
- Keep `graders/protected/` intact. Never weaken an oracle or test assertion.
- Large models, artifacts, and GGUFs remain on `E:\GameForge`.
- Agent-issued commands must remain allowlisted, shell-free, workspace-contained, and approval-gated.
- Pass `"think": False` when querying Ollama API programmatically.

