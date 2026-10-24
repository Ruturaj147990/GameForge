# GAMEFORGE IDE — CRITICAL DESKTOP UI REPAIR & FUNCTIONALITY AUDIT REPORT

**Date:** 2026-10-24  
**Status:** COMPLETE & VERIFIED  
**Architecture:** Native PySide6 (Windows 11 Qt 6) Desktop Application  
**Primary Model:** `gameforge-27b-sft:latest` (Ollama local inference)  
**Target Engine:** Unreal Engine 5.7.4 (`E:\UE\UE_5.7`)  
**Workspace:** `E:\gameforge_step1`  

---

## 1. Executive Summary

The native Windows GameForge IDE previously suffered from severe visual defects that rendered the chat and layout unusable:
1. **Chat Bubble Collapse (Critical P0):** Chat message bubbles were clamped to 30px height with scrollbars disabled, truncating all multi-line text and code blocks into unreadable horizontal smears.
2. **Terminal Dock Dominance (P1):** The embedded PowerShell terminal lacked initial dock sizing constraints in `QMainWindow`, consuming ~40% of the vertical screen height and severely squashing the central chat workspace.
3. **Contrast & Tofu Rendering (P0/P1):** A global `QWidget { background-color: #0d0f14; }` stylesheet rule was overriding child widget viewports, degrading contrast and causing layout bugs across platforms.
4. **Unreal Panel Status Discrepancies (P1):** The Unreal panel reported Engine Version 5.7.4 as detected but showed a blank installation path and reported `UAT Available: ❌ No`, while 64 repetitive-looking project entries clogged the project list.
5. **Streaming & Async Generator Cleanup (P1):** Early returns from the agent streaming loop left asynchronous generators unclosed, causing `RuntimeWarning: coroutine method 'aclose' was never awaited`.

All root causes were diagnosed, repaired in source code, verified with live offscreen/onscreen window captures, and validated against 172 unit tests and 45 protected benchmark graders (217 total tests, 0 failures).

---

## 2. Defects Diagnosed & Root Causes

| ID | Component | Severity | Observed Symptom | Root Cause | Repair Summary | Retest Result |
|---|---|---|---|---|---|---|
| **DEF-001** | `chat_panel.py` (`_MessageBubble`) | **P0** | Chat text clipped into 30px unreadable sliver; code invisible | `_content.document().size().height()` evaluated before layout returned 1; `setFixedHeight(min(max(doc_height, 30), 600))` clamped height to 30px with `ScrollBarAlwaysOff`. | Replaced with auto-sizing `QTextBrowser` with markdown support; dynamically calculates document height on viewport resize without arbitrary ceiling. | **VERIFIED** — Multi-line responses and 30-line C++ code blocks display completely without clipping. |
| **DEF-002** | `main_window.py` | **P1** | Bottom terminal dock consumed ~380px vertical space | `QMainWindow` lacked `resizeDocks` initialization for dock areas; bottom dock defaulted to ~40% window height. | Added `setCorner` configuration and explicit proportional `resizeDocks([_dock_terminal], [160], Qt.Vertical)`. | **VERIFIED** — Terminal sits cleanly at 160px height; chat area receives 650px+ vertical space. |
| **DEF-003** | `dark_theme.py` | **P0** | Global widget style override; child containers inheriting solid black backgrounds | `QWidget { background-color: #0d0f14; }` was applied indiscriminately to all QWidget subclasses. | Removed root `QWidget` background override; scoped background colors to top-level containers (`QMainWindow`, `QDialog`, `QDockWidget > QWidget`). | **VERIFIED** — High contrast palette (>12:1 ratio) with crisp Segoe UI typography and bright role borders. |
| **DEF-004** | `unreal_tools.py` & `unreal_panel.py` | **P1** | Unreal 5.7 detected but Install Path empty and UAT reported unavailable | Tool returned `engine_root` instead of `install_path`; UAT check looked for non-existent hardcoded path instead of `Engine\Build\BatchFiles\RunUAT.bat`. | Added `install_path`, verified `RunUAT.bat` presence (`E:\UE\UE_5.7\Engine\Build\BatchFiles\RunUAT.bat`), and updated panel UI row keys. | **VERIFIED** — Install Path displays `E:\UE\UE_5.7`; UAT reports `✅ Yes (RunUAT)`. |
| **DEF-005** | `unreal_tools.py` | **P2** | 64 duplicate-looking `GameForgePilot` entries in project list | `find_uprojects()` blindly searched all subdirectories including `reports/`, `scratch/`, `Intermediate/`, `Saved/`, and `Binaries/`. | Filtered out build/temp directories; formatted project items with relative directory tags (`🎮 GameForgePilot [fixtures/unreal/...]`). | **VERIFIED** — Deduplicated list showing only canonical workspace test fixtures. |
| **DEF-006** | `terminal_panel.py` & `chat_panel.py` | **P2** | "Clear" button clipped as "lea"; "New Session" clipped as "New Sessior" | Fixed button widths (`48px` and `100px`) were too narrow for text plus padding under standard Windows scaling. | Set minimum widths with dynamic layout sizing (`min-width: 58px` for Clear, `min-width: 110px` for New Session). | **VERIFIED** — Button text renders completely with zero truncation. |
| **DEF-007** | `agent_service.py` | **P1** | `RuntimeWarning: coroutine method 'aclose' was never awaited` on task stream termination | Async generator `stream_gen` was abandoned on loop `return` without `await stream_gen.aclose()`. | Wrapped streaming loop in `try...finally: await stream_gen.aclose()` and added `loop.shutdown_asyncgens()` in `run()`. | **VERIFIED** — Clean thread termination on task completion and user cancellation with zero warnings. |
| **DEF-008** | `main_window.py` | **P2** | Inability to quickly collapse/expand terminal from main toolbar | Only keyboard shortcut `Ctrl+``` and menu were available. | Added toggleable "⬛ Terminal" action button to the main top toolbar. | **VERIFIED** — 1-click workspace maximization to hide/show terminal. |

---

## 3. Code Modifications Summary

1. **`src/gameforge_ide/desktop/panels/chat_panel.py`:**
   - Overhauled `_MessageBubble` into an auto-sizing `QTextBrowser` supporting rich markdown, C++ code syntax highlighting, role badges (`USER`, `ASSISTANT`, `TOOL`, `SYSTEM`, `ERROR`), and a 1-click "Copy" button.
   - Implemented smart scroll tracking: generation auto-scrolls only if the user is already at the bottom; if the user scrolls up, text streaming does not hijack scroll position.
   - Refactored input composer: `Enter` or `Ctrl+Enter` dispatches prompts; `Shift+Enter` inserts newlines. Preserves prompt on recoverable failures.
   - Enlarged Send and Stop buttons (96×34px) with accessible state indicators.

2. **`src/gameforge_ide/desktop/styles/dark_theme.py`:**
   - Designed high-contrast studio dark palette: `#0c0e14` app chrome, `#121622` dock panels, `#181f30` raised cards, `#f3f4f8` primary text, `#9ca3af` secondary text.
   - Accent hierarchy: `#6366f1` (primary branding/buttons), `#00d9a3` (assistant/Unreal), `#f59e0b` (tools/busy), `#ef4444` (errors).
   - Removed destructive `QWidget` background inheritance.

3. **`src/gameforge_ide/desktop/main_window.py`:**
   - Configured `QMainWindow` corner ownership (`setCorner`) so Explorer and Unreal sidebars flank the central workspace cleanly.
   - Enforced initial dock dimensions via `resizeDocks` (Explorer: 260px, Unreal: 340px, Terminal: 160px).
   - Added toolbar Terminal toggle button (`_act_tb_terminal`) bidirectionally synchronized with dock visibility.

4. **`src/gameforge_ide/desktop/panels/unreal_panel.py` & `backend/tools/unreal_tools.py`:**
   - Resolved UE 5.7 detection: verified canonical installation path `E:\UE\UE_5.7` and `RunUAT.bat`.
   - Formatted project listing to show relative project directory context (`[fixtures/unreal/...]`).
   - Excluded build artifacts, `reports`, `scratch`, and `Intermediate` folders from `.uproject` scan.

5. **`src/gameforge_ide/desktop/panels/terminal_panel.py`:**
   - Fixed header button clipping by expanding `btn_clear` to minimum width 58px and `btn_restart` to 30px.

6. **`src/gameforge_ide/desktop/services/agent_service.py`:**
   - Added `await stream_gen.aclose()` in streaming `finally:` block.
   - Added `loop.shutdown_asyncgens()` in `run()` worker method.

7. **`src/gameforge_ide/backend/tools/edit_tools.py`:**
   - Added parameter fallback supporting both `subpath` and `file_path` in `propose_edit`.

8. **`tests/unit/test_desktop_acceptance.py`:**
   - Added automated regression tests 7 through 10 verifying bubble auto-sizing, dock proportions, UAT detection display, and async worker cleanup.

---

## 4. Verification Evidence

- **Baseline Defect Capture:** `reports/screenshot_before_repair.png`
- **Post-Repair Chat & Code View:** `reports/screenshot_after_repair.png`
- **Multi-turn Conversation View:** `reports/screenshot_chat_conversation.png`
- **Diff Review Approval & Rollback View:** `reports/screenshot_diff_review.png`
- **Terminal Collapsed View:** `reports/screenshot_terminal_collapsed.png`
- **Windows High-DPI (125%) View:** `reports/screenshot_dpi_125.png`
- **Live Model Streaming View:** `reports/screenshot_live_streaming.png`
- **Unit Test Suite:** 172 passed in 7.58s
- **Protected Oracle Graders:** 45 passed in 0.05s
- **Total Tests Passing:** 217 passed, 0 failed.
