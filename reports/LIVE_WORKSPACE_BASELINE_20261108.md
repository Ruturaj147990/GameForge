# GameForge — Live Workspace Baseline Report
**Date:** 2026-11-08T12:55:00+05:30  
**Host:** Windows 11 Pro, AMD Ryzen 5 7600X, 32 GB DDR5, Radeon RX 7700 XT 12 GB  
**Canonical Repo Root:** `E:\gameforge_step1`  
**Large-Project / Artifact Root:** `E:\GameForge`  

---

## 1. Git State & Working Tree
- **Active Branch:** `master`
- **HEAD Commit:** `b7618403e730612e894f407ab51d3dd02fa56ae5`
- **Git Status:** Clean working tree, ahead of `origin/master` by 5 commits
- **Submodules:** None

---

## 2. Environment Verification

| Component | Verified Local State | Evidence / Source |
|---|---|---|
| **Python** | 3.14.6 | `python --version` |
| **PySide6** | 6.12.0 | `python -c "import PySide6; print(PySide6.__version__)"` |
| **PyInstaller** | 6.22.3 | `pyinstaller --version` (on PATH) |
| **Ollama Daemon** | Active (PID 17172) on `127.0.0.1:11434` | `Get-Process ollama`, HTTP `/api/tags` |
| **Local Models** | `gameforge-qwen3.5-9b:latest` (`278e024c31f7`), `gameforge-qwen3.5-4b:latest` (`91b2043beeee`), `gameforge-27b-sft:latest` (`03d36e692be8`), `llama3.1:8b` (`46e0c10c039e`) | `curl.exe http://127.0.0.1:11434/api/tags` |
| **Unreal Engine** | 5.7.4-51494982+++UE5+Release-5.7 at `E:\UE\UE_5.7` | `Engine/Build/Build.version` |
| **Unreal Color API** | `FLinearColor::Gray` (line 457) and `FColor::Orange` (line 758) | `E:\UE\UE_5.7\Engine\Source\Runtime\Core\Public\Math\Color.h` |

---

## 3. Protected Grader Baseline Hashes (SHA-256)

All protected grader files remain intact, immutable, and strictly guarded against modification:

| SHA-256 Hash | Relative Path |
|---|---|
| `6317760d87ef79cd83cb11d01192df43ad127635eab4494ec007a40a26bce660` | `graders/protected/t2_004/test_health_damage_hidden.py` |
| `3ff897a864c6e5a5567fe04f433729f7732c81f8b96f7b82c31232ac53912166` | `graders/protected/t2_005/test_pickup_collection_hidden.py` |
| `41c198dad0802db30c7532680c4ecbcf809783019aa72a026ba5af5341a3d3da` | `graders/protected/t2_008/test_projectile_collision_hidden.py` |
| `69694c4bb7b2e05a0b52a09c419431da315de57c566b7172a298a5c4e5d95bcd` | `graders/protected/t3_016/test_player_composition_hidden.py` |
| `70f8efb8df4be7f3cd9e8f44c57c92f613f8bc306e6be5382c375ffcce140c92` | `graders/protected/t3_017/test_health_stamina_hud_hidden.py` |

---

## 4. Test Suite Baseline Results

- `graders/protected/`: **45 passed, 0 failed** in 0.05s [VERIFIED]
- `tests/gameforge_1_0/`: **99 passed, 0 failed** in 17.77s [VERIFIED]
- Total unique pytest test node IDs collected across repository: **1,613 unique test items** [VERIFIED]
  - `tests/unit/`: 1,493 items
  - `tests/gameforge_1_0/`: 99 items
  - `graders/protected/`: 45 items
  - Integration: `tests/integration/test_studio_walk.py`: 1 item

---

## 5. Confirmed Issues & Defects at Baseline

1. **P0 Raw Tool JSON Leak:** User chat receives raw JSON tool calls (e.g. `{"command": "read_file", "path": "..."}`) because parser and UI detectors do not handle flat `command` dictionaries and rely on prefix matching.
2. **P0 Unreal C++ Color Constant & Invariant Errors:** `FLinearColor::Grey` and `FLinearColor::Orange` fail MSVC compilation in UE 5.7.4; `CounterStrike/Source/CounterStrike/GFGameImpl.h` has invalid `override` specifiers on non-virtual methods.
3. **P0 Cancellation Transport:** `OllamaProvider.chat_with_tools()` uses blocking non-streamed `urllib` requests with non-cancellable worker execution.
4. **P0 Thread Lifecycle:** `AgentService.shutdown()` relies on `QThread.terminate()`, which risks corruption; `stop()` invokes `_ensure_runtime()` on GUI thread if runtime is uninitialized; workspace switching races with worker thread.
5. **P0 Context Budget Propagation:** `fit_history_to_context()` computes adapted `output_tokens` but callers use the stale initial reservation; native tool schemas are not accounted for in preflight budget.
6. **P0 Approval Capabilities & Boundary:** Approval IDs lack strict regex validation before path construction; approval resume accepts caller-supplied `tool_result` without verified execution receipt; `.gameforge/approvals` needs explicit write protection.
7. **P0 Shell Mismatch:** `TerminalTools.run_command()` defaults missing shell to `direct`, while `ToolGateway` classifies with `args.get("shell", "powershell")`.
8. **P1 Chat UI Visual Rhythm:** Assistant messages are rendered inside heavy bordered cards; activity items need compact inline presentation without leaking raw JSON.
