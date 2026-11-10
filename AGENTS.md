# GameForge — Codex Agent Guidelines & Operating Protocol
# Current Directory: E:\GameForge_IDE (Unreal-Exclusive Studio & IDE)

## Mandatory Ecosystem Architecture & Operating Rules

All Codex agents, subagents, and sessions operating within the GameForge ecosystem must strictly follow these non-negotiable rules. Engineering continuity across context compactions, session restarts, and reboots depends on this durable workflow.

### 1. Strict No-Duplicate-Files Rule
- **NEVER create duplicate files or duplicate mirror folders across the filesystem.**
- Do not create local copies, redundant backups, or sidecar duplicates of files belonging to other directories.
- If an AI agent needs to inspect, reference, or modify a file belonging to another part of the ecosystem, **the agent MUST navigate directly to that designated canonical directory and edit or read the file in place.**
- Agents must be aware of the canonical directory map (see below) to immediately know where files reside.

### 2. Strict Centralized Documentation Rule
- **ALL `context.md` files, architecture contracts, roadmaps, decision logs, specifications, and ledgers reside EXCLUSIVELY in `E:\GameForge_Documentation`.**
- **NEVER create, copy, or mirror `context.md` into `E:\GameForge_IDE` or any other directory.** There is only ONE canonical `context.md` across the entire machine: `E:\GameForge_Documentation\context.md`.
- For all documentation reading and writing:
  1. Navigate directly to `E:\GameForge_Documentation\`.
  2. Perform reading, editing, or updating in place at `E:\GameForge_Documentation\context.md` or `E:\GameForge_Documentation\docs\`.
  3. Never scatter markdown documentation, meeting notes, audit logs, or CSV registers in local source folders.

### 3. Blocked Non-Unreal Engines Rule
- GameForge is strictly **Unreal Engine 5.7.4 exclusive**.
- All non-Unreal engine repositories (`E:\GameForge_Unity`, `E:\GameForge_Godot`, `E:\GameForge_Roblox`, `E:\GameForge_Bevy`, `E:\GameForge_GameMaker`, `E:\GameForge_O3DE`) are **STRICTLY BLOCKED** from active GameForge IDE operations.
- Active GameForge agents must NOT import, link, invoke, or mutate any files inside these separated engine folders.

---

## Canonical Ecosystem Directory Map & Navigation Guide

When performing any task, navigate directly to the authoritative directory:

| Canonical Directory | Role & Responsibility | Tech Stack / Contents | When an Agent Navigates Here |
|---|---|---|---|
| `E:\GameForge_IDE\` | **Unreal-Exclusive IDE Platform** | Python 3.10+, PySide6, FastAPI, Pydantic | To modify Desktop Studio UI, agent runtime, IDE toolchains, prompts, and code synthesizers. |
| `E:\GameForge_Unreal_Plugin\` | **Authoritative Unreal Engine Plugin** | C++20, UE 5.7.4, 129 Python Ops, MSVC 14.44 | To edit native C++ plugin code (`GameForge.uplugin`), editor extensions, or Python Ops. |
| `E:\GameForge_AI_Models\` | **Model Weights & Inference Serving** | Ollama Daemon (`localhost:11434`), GGUF, SafeTensors | To inspect model weights, verify Ollama models, or manage LLM storage. |
| `E:\GameForge_AI_Training\` | **Fine-Tuning Pipelines & Datasets** | ROCm 6.x, PyTorch, LoRA adapters, SFT datasets | To inspect or execute fine-tuning runs, format datasets, or manage training lineage. |
| `E:\GameForge_Benchmarks\` | **Independent QA & Protected Graders** | Python CLI (`gameforge-bench`), 45 Protected Oracles | To run evaluation benchmarks, execute protected grader tests, or manage eval tasks. |
| `E:\GameForge_Projects\` | **User Games & Generated Workspaces** | Unreal Engine `.uproject`, C++, Assets, Binaries | To inspect, run, or debug synthesized user games (e.g., Sudoku, Ludo). |
| `E:\GameForge_Engine_Testbed\` | **Real Engine Automation Testbed** | 43 GB Unreal 5.7.4 Testbed (`GFKitTest.uproject`) | To run live Unreal automation tests (`Automation RunTests`), cook, or package. |
| `E:\GameForge_Documentation\` | **Canonical Ecosystem Documentation** | `context.md`, `docs/`, `DECISION_LOG.csv`, `ECOSYSTEM_MAP.md` | **To read or write ANY documentation, project history, roadmaps, or architecture specs.** |

---

## E:\GameForge_IDE Specific Operating Protocols

1. **Native IDE Entry Point**: `python -m src.gameforge_ide.launcher`; use `--serve` only for the loopback Unreal bridge (`localhost`, `127.0.0.1`, or `::1`).
2. **Native IDE Preferences**: Studio Dark/Light, geometry, and dock state persist in `.gameforge/ide_settings.ini`; use Ctrl+T to switch themes and View → Reset Layout to restore default docks.
3. **Execution Commands**:
   - Unit tests: `pytest tests/unit/`
   - Graders: `pytest graders/protected/` (when testing against local benchmark suite)
   - Benchmark evaluation: navigate to `E:\GameForge_Benchmarks` and run `pytest` there.
4. **Hardware & Inference Constraints**:
   - Hardware: Ryzen 5 7600X, 32GB DDR5, RX 7700 XT 12GB VRAM.
   - Inference: Always pass `"think": False` when querying Ollama API programmatically.
   - Dynamic Synthesis: Never hardcode specific games or keyword shortcuts. All mechanics, layouts, and C++ code must be dynamically synthesized.
5. **Automation Safety**: Automation closing the IDE must set `win.confirm_on_close = False` before `win.close()` to avoid modal dialog hangs.
