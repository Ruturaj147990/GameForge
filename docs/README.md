# GameForge Knowledge Base

The authoritative engineering documentation for GameForge, a Windows desktop platform that turns natural-language
game ideas into playable, verified Unreal Engine 5 games. **Start with `context.md` at the repository root** (current
state and next action), then read the documents below in this order.

| # | Document | Purpose | Who updates it |
|---|---|---|---|
| 0 | [`00_STATUS.md`](00_STATUS.md) | Live capability matrix with evidence links | Antigravity per work item; Claude reviews |
| 1 | [`01_ARCHITECTURE.md`](01_ARCHITECTURE.md) | Product definition, design contract, security rules, components, data contracts, decision register (AD-1…AD-20) | Claude only |
| 2 | [`02_AUDIT_2026-10-31.md`](02_AUDIT_2026-10-31.md) | Full audit of the code as of 2026-10-31: findings F-01…F-21 | frozen (dated) |
| 3 | [`03_RESEARCH_2026-10-31.md`](03_RESEARCH_2026-10-31.md) | Research findings with sources and design consequences | frozen (dated) |
| 4 | [`04_ROADMAP.md`](04_ROADMAP.md) | **The only active plan**: phases P0–P11, gates, risks | Claude only |
| 5 | [`05_UX_SPEC.md`](05_UX_SPEC.md) | Studio UX: IA, views, components, accessibility, performance | Claude only |
| 6 | [`06_ENGINE_NOTES_UE57.md`](06_ENGINE_NOTES_UE57.md) | Verified UE 5.7.4 API lessons, plugin build and install, cooked-build rules | everyone (append lessons) |
| 7 | [`07_CONTENT_AND_MODELS.md`](07_CONTENT_AND_MODELS.md) | Models, specialist backends, asset lifecycle, provenance and licence classes | Claude; Antigravity adds measurements |
| 8 | [`08_TESTING_AND_EVIDENCE.md`](08_TESTING_AND_EVIDENCE.md) | Evidence rules, test layers, commands, baselines | everyone |
| H | [`handovers/`](handovers/) | `HANDOVER_PROTOCOL.md`, `QUESTIONS.md`, and one executable handover per phase (`P00`…`P11`) | Claude writes; Antigravity updates progress |
| G | `generated/` | Generated tables (op coverage), created in P0 WI-0.11 | scripts only |
| Hist | [`history/`](history/) | The old `context.md` log, defect ledgers, execution history, superseded reports | read-only |

## Other root files

| File | Status |
|---|---|
| `AGENTS.md` | Agent operating protocol (mandatory) |
| `context.md` | Canonical current state + next action (mirrored to `E:\GameForge\context.md`) |
| `ANTIGRAVITY_HANDOFF.md` | Pointer for Antigravity sessions |
| `DECISION_LOG.csv` | Decision ledger (D-001…); append only |
| `GAMEFORGE_FINAL_MASTER_STRATEGY.md`, `STEP4_AUDIT_REPORT.md`, `GAMEFORGE_ROADMAP.csv`, `TASK_INVENTORY.csv`, `ENGINE_FEATURE_COVERAGE_MATRIX.csv`, `EVALUATION_CONTRACT.md` | **Benchmark product line (frozen).** `gameforge_bench` and `tests/unit/test_acceptance_criteria.py` read them relative to the root, beside the protected `graders/`. Not plans for the IDE product |
| `docs/LEGAL_RIGHTS_CLEARANCE_PACKET_V2.md` | Legal record for the v2 training data (referenced by training scripts) |
| `reports/` | Raw evidence (JSON, PNG) and model-training reports |
