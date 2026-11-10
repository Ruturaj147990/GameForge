# GameForge — Codex Agent Guidelines & Operating Protocol

## Mandatory Project Context Protocol

All Codex agents, subagents, and sessions operating on the GameForge project must strictly follow this protocol. Engineering continuity across context compactions, session restarts, and reboots depends on this durable workflow.

### 1. At the Beginning of Every GameForge Task
1. **Locate and read the canonical `context.md`** at the repository root (`context.md`) before planning, investigating, or modifying the project.
2. **Treat `context.md` as the primary source of truth** for project history, hardware constraints, architecture decisions, and the current active objective.
3. **Verify relevant facts** against current source code, configuration files, and filesystem artifacts before relying on potentially stale information.
4. **Read any linked detailed reports** (e.g., in `reports/` or `UPGRADE_REPORT.md`) necessary for the requested task.
5. **Never ask the user to reconstruct or repeat information** already preserved in `context.md`.

### 2. During Every Task
1. **Preserve important discoveries as they occur**, especially before long-running operations (benchmarks, evaluations, builds), major edits, or context transitions.
2. **Update `context.md` at meaningful milestones** rather than waiting until the end of the session.
3. **Record consequential architecture decisions**, model configurations, test outcomes, resolved bugs, and remaining blockers.
4. **Reconcile changing facts immediately**: update the current-state section rather than allowing obsolete information to remain presented as current.
5. **Link to detailed reports and logs** instead of pasting lengthy raw outputs or source trees into `context.md`.
6. **Keep critical non-negotiable constraints visible and actionable**:
   - Hardware: Ryzen 5 7600X, 32GB DDR5, RX 7700 XT 12GB VRAM.
   - Storage & No Duplicate Files Rule: Never create duplicate files or duplicate mirror folders across the filesystem. Do not mirror `context.md` or create redundant copies across drives/directories. Agents must navigate/travel directly to the required target directory and modify files in place, without creating duplicate copies elsewhere.
   - Inference: Always pass `"think": False` when querying Ollama API programmatically.
   - Dynamic Prompt-to-Game Generation: Never hardcode specific test/demo games (e.g., Snake and Ladders, Zombie Survival, Sudoku) or secretly select predefined games by prompt keywords. Every prompt must dynamically synthesize custom mechanics, entities, rules, layouts, UI, and C++ logic tailored to the user's requirements.

### 3. Before Finishing Every Task
1. **Update `context.md`** with what was actually accomplished during the task.
2. **Record changed file paths**, current model tags, artifact SHA-256 digests, tests executed, and their exact outcomes.
3. **Explicitly state what remains incomplete** and define the next concrete action.
4. **Include ISO timestamps** for significant state changes.
5. **Ensure a future session can seamlessly resume** without needing access to the previous chat conversation.
6. **Save `context.md` and verify** that the file exists and is intact on disk.
7. **Single Source of Truth**: Do NOT duplicate or mirror `context.md` across multiple directories. Maintain only the canonical repository root file (`context.md`).

### 4. When Context is Compacted or a New Session Begins
- When context compaction occurs or a conversation nears token limits, immediately write an updated checkpoint to `context.md`.
- Preserve the active objective, verified findings, decisions made, completed steps, and the exact next step.
- Do not rely on conversation transcripts as the sole record.
- Do not assume compaction will automatically preserve project state without manual verification.

### 5. Instruction Precedence & Conflict Resolution
- Follow the user's latest explicit instructions above general defaults.
- Do not use stale context to override a current user request.
- Update `context.md` to reflect a new direction only when supported by explicit user direction or verified empirical evidence.
- Distinguish evidence states: `[VERIFIED]`, `[REPORTED]`, `[UNVERIFIED]`, `[BLOCKED]`, and `[SUPERSEDED]`.

## Codex Project Quick Reference

- Canonical source repository: workspace root; large artifacts and mirrored context: `<data_root>` from the active host profile (`configs/host_profiles/*.json`).
- Native IDE entry point: `python -m src.gameforge_ide.launcher`; use `--serve` only for the loopback Unreal bridge (`localhost`, `127.0.0.1`, or `::1`).
- Native IDE preferences (Studio Dark/Light, geometry, and dock state) persist in the selected workspace's `.gameforge/ide_settings.ini`; use Ctrl+T to switch themes and View → Reset Layout to restore the default docks.
- Test commands: `pytest tests/unit/` and `pytest graders/protected/` (when benchmark graders are installed alongside the source tree). If the sandbox denies its C: temporary directory, create `scratch/pytest_os_temp` and set `TEMP` and `TMP` to that path for the test process only.
- Keep `graders/protected/`, model weights, Ollama blobs, datasets, training lineage, legal records, and user changes intact. Never weaken a protected oracle.
- Agent-issued command execution must remain allowlisted, shell-free, workspace-contained, and approval-gated. The embedded terminal is user-controlled and is not an OS sandbox.
- Before packaging, obtain approval to install a packager; current host requires PySide6 >= 6.6.0. Do not bundle model weights.
- Knowledge base: `docs/README.md` (index). Active plan: `docs/04_ROADMAP.md` (phases P0–P11). Executable work: `docs/handovers/P<nn>_*.md`, following `docs/handovers/HANDOVER_PROTOCOL.md`. Design contract and security rules: `docs/01_ARCHITECTURE.md` §1. Engine lessons: `docs/06_ENGINE_NOTES_UE57.md`. Verification commands and evidence rules: `docs/08_TESTING_AND_EVIDENCE.md`. Live capability status: `docs/00_STATUS.md`.
- Real engine paths only: `unreal/live_editor.py` (editor), `unreal/toolchain.py` (build/test/package), `pipeline/game_pipeline.py` (prompt → game). Classes marked `simulated: True` are test doubles, never evidence.
- Automation that closes the IDE must set `win.confirm_on_close = False` before `win.close()`, or it blocks on the "Are you sure?" dialog.
