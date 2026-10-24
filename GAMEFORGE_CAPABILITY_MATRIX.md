# GameForge IDE Capability Matrix

**Updated:** 2026-10-24T18:15:45+05:30  
**Evidence boundary:** Source inspection, 195 unit and 45 protected tests, UE 5.7.4 package build/editor load, authenticated editor-originated context sync via console command, live local model/provider smoke, and native UI reply. AgentRuntime/desktop model streaming and populated Unreal selection/asset transfer remain unverified.

The full machine-readable UI interaction registry is [`configs/ui_interaction_registry.json`](configs/ui_interaction_registry.json). It records stable IDs, handlers, preconditions, permissions, state transitions, feedback, cancellation and test evidence for the implemented menus, toolbar, chat, explorer, diff, Unreal, terminal, shortcuts and command palette. The registry also lists controls intentionally absent or disabled.

| Stable ID / control | Panel | Action / handler | Permission or precondition | Verified status |
|---|---|---|---|---|
| `tb_new_session`, `file_new_session` | Main window | Create a new persisted chat session | None | Wired; session persistence test exists |
| `tb_clear_chat`, `btn_clear_chat` | Toolbar / Chat | Clear visible conversation | None; does not delete session history | Wired |
| `tb_check_ollama` | Toolbar | Query local Ollama health | Local daemon available | Wired; daemon/model registry and direct API smoke responded in this checkpoint; UI health button not manually exercised |
| `tb_toggle_terminal`, `view_terminal` | Main window | Show/hide terminal dock | None | Wired; toggle test exists |
| `view_explorer` | View menu | Show/hide Explorer dock | None | Wired |
| `view_unreal` | View menu | Show/hide Unreal dock | None | Wired |
| `view_diff` | View menu | Show/hide Diff Review dock | None | Wired |
| `view_toggle_theme` / Ctrl+T | View menu | Switch Studio Dark/Light and persist choice | None | Wired; inline palette round-trip and preference restoration tested |
| `view_reset_layout` | View menu | Restore default dock state and window size | None | Wired; hide/reset and saved dock-visibility restoration tested |
| `command_palette` / Ctrl+K | Help menu / Main window | Search and dispatch supported commands | Search text or choose a listed command | Wired; filter and dispatch tested |
| `chat_slash_commands` | Chat | Execute developer slash commands (`/build`, `/ue`, `/context`, `/clear`, `/new`, `/diff`, `/terminal`, `/help`) | Slash prefix in prompt composer | Wired; direct local dispatch tested |
| `chat_chips_bar` | Chat | One-click context chips (`@ue`, `@actor`, `@asset`, `⚙ /build`, `🗑 /clear`) | Chat panel active | Wired; composer token insertion tested |
| `chat_unreal_sync_badge` | Chat status bar | Live Unreal Editor context indicator | Workspace `.gameforge/unreal_context.json` present | Wired; periodic sync and badge update tested |
| `file_quit` / Ctrl+Q | File menu | Close application | Confirmation dialog unless disabled by test harness | Wired |
| `model_combo` | Chat | Select model for session | Model must be listed by provider | Wired; live model listing not verified now |
| `btn_new_session` | Chat | Create a new session | None | Wired |
| `btn_send` / Enter | Chat | Persist and send exact composer text through runtime/provider history | Non-whitespace prompt and active session | Wired; boundary whitespace, multiline Unicode, long payload, session refresh, payload JSON, and stream parser covered |
| `agent_context_summary` | Agent runtime | Include canonical identity, constraints, and active objective in system prompt | Workspace `context.md` available | Section-aware selection tested with current objective after line 50; character cap marks truncation |
| `agent_context_budget` | Agent runtime / Chat | Keep complete current prompt and newest whole history messages within estimated provider input capacity | Provider declares context size | UTF-8 heuristic budget tests preserve full current prompt, omit older history and reject impossible budget without truncation; chat explains omitted messages |
| `btn_stop` | Chat | Request cancellation and wait for worker completion | Agent busy | Wired; busy remains until done/error and session switch ignores late old-task events |
| `btn_copy_bubble` | Message bubble | Copy rendered message's source text | Clipboard available | Wired; covered in sizing/render test |
| `btn_explorer_refresh` | Explorer | Repopulate workspace root | Workspace accessible | Wired |
| `explorer_search` | Explorer | Filter workspace listing | None | Wired |
| `btn_approve` | Diff Review | Apply reviewed diff | Pending diff; explicit click | Wired; gateway-approved route and lifecycle covered |
| `btn_reject` | Diff Review | Reject pending diff | Pending diff | Wired |
| `btn_rollback` | Diff Review | Restore pre-edit bytes | Applied diff still matches expected digest; explicit click | Wired; stale protection tested |
| `btn_ue_refresh` | Unreal | Refresh engine and project discovery | None | Wired; panel discovery tests exist |
| `btn_ue_build` | Unreal | Run staged Unreal build | Project selected; explicit button click | Wired through approved path; real build unverified |
| `btn_term_clear` | Terminal | Clear terminal output view | None | Wired |
| `btn_term_restart` | Terminal | Restart user PowerShell process | None | Wired; process recovery unverified |
| `btn_term_run` / Enter | Terminal | Send command to embedded PowerShell | User-controlled terminal | Wired; not agent sandboxed |

## Missing or unverified controls

- The Light palette, live rich-text recoloring, and saved geometry/dock state are implemented. Real Windows DPI-scale and minimum-size visual checks remain unverified.
- Session rename/search/delete/export UI and an integrated build/test diagnostics panel are not present in the current native UI.
- Unreal 5.7.4 Win64 plugin package compilation/editor load and authenticated editor-originated context sync passed via `GameForge.SyncContext`. Menu click was not automated; selected actor/open-asset fields were empty in the disposable host.
- The generic agent command tool is intentionally held behind gateway approval and is not currently exposed with an approval dialog; the embedded terminal remains a separate user-driven PowerShell.
- The complete registry is source/test evidence, not an exhaustive manual accessibility audit. Some entries explicitly mark their test as manual or unverified; they must not be interpreted as validated workflows.
