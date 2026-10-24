# GameForge — Antigravity Agent Guidelines & Operating Protocol

## Mandatory Project Context Protocol

All Antigravity agents, subagents, and sessions operating on the GameForge project must strictly follow this protocol. Engineering continuity across context compactions, session restarts, and reboots depends on this durable workflow.

### 1. At the Beginning of Every GameForge Task
1. **Locate and read the canonical `context.md`** at the repository root (`E:\gameforge_step1\context.md`) before planning, investigating, or modifying the project.
2. **Treat `context.md` as the primary source of truth** for project history, hardware constraints, architecture decisions, and the current active objective.
3. **Verify relevant facts** against current source code, configuration files, and filesystem artifacts before relying on potentially stale information.
4. **Read any linked detailed reports** (e.g., in `reports/gameforge-27b-sft/`) necessary for the requested task.
5. **Never ask the user to reconstruct or repeat information** already preserved in `context.md`.

### 2. During Every Task
1. **Preserve important discoveries as they occur**, especially before long-running operations (benchmarks, evaluations, builds), major edits, or context transitions.
2. **Update `context.md` at meaningful milestones** rather than waiting until the end of the session.
3. **Record consequential architecture decisions**, model configurations, test outcomes, resolved bugs, and remaining blockers.
4. **Reconcile changing facts immediately**: update the current-state section rather than allowing obsolete information to remain presented as current.
5. **Link to detailed reports and logs** instead of pasting lengthy raw outputs or source trees into `context.md`.
6. **Keep critical non-negotiable constraints visible and actionable**:
   - Hardware: Ryzen 5 7600X, 32GB DDR5, RX 7700 XT 12GB VRAM.
   - Storage: All large artifacts, models, GGUFs, and datasets must stay on `E:\GameForge`.
   - Safety: **NEVER shut down, restart, sleep, or hibernate the system. Never invoke `shutdown.exe`.**
   - Inference: Always pass `"think": False` when querying Ollama API programmatically.

### 3. Before Finishing Every Task
1. **Update `context.md`** with what was actually accomplished during the task.
2. **Record changed file paths**, current model tags, artifact SHA-256 digests, tests executed, and their exact outcomes.
3. **Explicitly state what remains incomplete** and define the next concrete action.
4. **Include ISO timestamps** for significant state changes.
5. **Ensure a future session can seamlessly resume** without needing access to the previous chat conversation.
6. **Save `context.md` and verify** that the file exists and is intact on disk.
7. If operating across multiple locations, mirror `context.md` to `E:\GameForge\context.md`.

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
