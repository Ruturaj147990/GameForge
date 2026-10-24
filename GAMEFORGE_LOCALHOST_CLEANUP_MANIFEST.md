# GameForge IDE — Localhost & Legacy Web UI Cleanup Manifest

**Date:** 2026-10-24  
**Authority:** Product-Priority Decision D-030 and `GAMEFORGE_FINAL_MASTER_STRATEGY.md`  
**Purpose:** Record the permanent deletion of obsolete localhost web interface files and the retention of required in-process and loopback communication services.

---

## 1. Cleanup Policy and Classification Rules

Every candidate file and code path was evaluated against the following criteria:
- **`REMOVE`**: Pure legacy browser assets (HTML, CSS, browser JavaScript) and static-file mounting code superseded by native PySide6 desktop panels.
- **`REFACTOR`**: Code modified to remove browser/static dependencies while keeping essential services.
- **`KEEP`**: Essential desktop UI, in-process agent runtime, local Ollama integration, session management, tool execution, and the minimal loopback Unreal Engine 5.7 plugin HTTP bridge (`--serve`).

---

## 2. Inventory of Removed Assets

| Relative Path | Size | Former Role | Reason for Deletion | Action |
| :--- | :---: | :--- | :--- | :---: |
| `src/gameforge_ide/frontend/app.js` | 16,578 B | Legacy browser WebSocket and chat controller | Superseded by native `ChatPanel` and `AgentService` Qt signals. | **DELETED** |
| `src/gameforge_ide/frontend/index.html` | 12,868 B | Legacy single-page browser shell | Superseded by native `MainWindow` (`QMainWindow`). | **DELETED** |
| `src/gameforge_ide/frontend/style.css` | 12,185 B | Legacy CSS stylesheet for browser DOM | Superseded by native QSS `dark_theme.py`. | **DELETED** |
| `src/gameforge_ide/frontend/` | Directory | Obsolete frontend asset folder | Entire directory purged from filesystem. | **DELETED** |

**Total Reclaimed Disk Space:** **41,631 bytes (40.66 KB)**.

---

## 3. Inventory of Retained and Refactored Services

| Component | Path | Retained Purpose | Classification |
| :--- | :--- | :--- | :---: |
| **Launcher** | `src/gameforge_ide/launcher.py` | Default launches native PySide6 IDE; `--serve` launches headless FastAPI backend. | `KEEP` |
| **FastAPI Backend** | `src/gameforge_ide/backend/app.py` | Minimal loopback HTTP server required for Unreal Engine 5.7 plugin context synchronization (`/api/unreal/context`) and health checks (`/api/health`). Static files mount removed. | `REFACTOR` |
| **Agent Runtime** | `src/gameforge_ide/backend/agent/runtime.py` | Core 14-step bounded agentic loop called in-process by native `AgentService`. | `KEEP` |
| **Tool Gateway** | `src/gameforge_ide/backend/tools/gateway.py` | Typed tool execution engine called in-process by native `ToolService`. | `KEEP` |
| **Ollama Provider** | `src/gameforge_ide/backend/providers/ollama_provider.py` | Direct HTTP client connecting to local Ollama (`127.0.0.1:11434`). | `KEEP` |
| **Session Manager** | `src/gameforge_ide/backend/session_manager.py` | Disk-persisted conversation history stored in `.gameforge/sessions/`. | `KEEP` |
| **Unreal 5.7 Plugin** | `src/gameforge_ide/unreal/GameForge/` | C++ Editor plugin sending editor context to IDE over loopback. | `KEEP` |

---

## 4. Verification Check

Following the deletion of `src/gameforge_ide/frontend/`:
1. `python -c "import src.gameforge_ide"` succeeded with exit code 0.
2. `pytest tests/unit/` executed with **168 passed in 13.18 seconds (100% pass rate)**.
3. Protected benchmark oracles (`pytest graders/protected/`) executed with **45 passed in 0.03 seconds (100% pass rate)**.
4. Zero broken imports or dangling static asset references exist in the repository.
