# P4 — Studio UX v2 (handover)

**Branch:** `master` (no feature branches). **Depends on:** P1–P3 accepted. **Decision:** AD-18. **Spec:** `../05_UX_SPEC.md` (normative:
read it fully). **Estimate:** 2–3 weeks. **Resolves:** F-14.

## Objective

Rebuild the IDE shell around the product loop on real data (GDS from P1, Forge runs from P2, scenarios from P3),
without regressing resource budgets or any existing test. Migration is **side by side**: the new shell is built while
the old docks keep working in the Code view, and nothing is deleted until its replacement has passing tests.

## Rules for this phase

- Views never import backend modules that do I/O on the UI thread. Every load goes through
  `core.jobs.JobManager.submit`, and the result returns through a Qt signal (`forge_service` pattern from WI-2.8).
- Every new widget sets `objectName` (tests find widgets by it) and `setAccessibleName`.
- Colours and sizes come only from `desktop/styles/tokens.py`. A unit test greps `desktop/views/` for `#[0-9a-fA-F]{6}`
  literals and fails if it finds any (excluding `styles/`).
- The legacy shell stays available behind `GAMEFORGE_LEGACY_SHELL=1` until the phase exit gate passes. It is removed in
  the last work item.

## Package layout

```
src/gameforge_ide/desktop/
  assets/icons/*.svg                  # WI-4.1
  icons.py                            # icon loader
  shell/__init__.py  top_bar.py  rail.py  view_host.py  assistant_panel.py  toasts.py  palette.py
  services/systems_service.py         # readiness probes (Qt-free core in core/systems.py)
  services/projects_service.py        # games list, thumbnails
  views/home_view.py games_view.py design_view.py build_view.py play_view.py evidence_view.py
        assets_view.py code_view.py settings_view.py onboarding.py
  widgets/ cards.py empty_state.py status_dot.py step_row.py log_view.py problems_table.py gds_form.py rule_editor.py
src/gameforge_ide/core/systems.py     # SystemsSnapshot dataclass + probe functions (Ollama, engine, disk, RAM, editor link)
```

---

## WI-4.1 Icon system

Create these SVG files (copy the path data exactly). All use the same wrapper:
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"
     stroke-linecap="round" stroke-linejoin="round"><path d="…"/></svg>
```

| File | `d` attribute |
|---|---|
| `home.svg` | `M3 11 12 3l9 8v10h-6v-6H9v6H3z` |
| `games.svg` | `M6 8h12a4 4 0 0 1 4 4v3a3 3 0 0 1-5.4 1.8L15 15H9l-1.6 1.8A3 3 0 0 1 2 15v-3a4 4 0 0 1 4-4z M7 10.5v3 M5.5 12h3 M16 11.5h.01 M18 13h.01` |
| `design.svg` | `M6 3h9l4 4v14H6z M14 3v5h5 M9 12h7 M9 16h5` |
| `build.svg` | `M4 6h16 M4 12h11 M4 18h6` |
| `play.svg` | `M7 4l13 8-13 8z` |
| `evidence.svg` | `M4 5h16v14H4z M4 16l4-4 3 3 4-5 5 6 M9 9h.01` |
| `assets.svg` | `M12 3l8 4.5v9L12 21l-8-4.5v-9z M12 12l8-4.5 M12 12v9 M12 12L4 7.5` |
| `code.svg` | `M8 7l-5 5 5 5 M16 7l5 5-5 5` |
| `settings.svg` | `M4 6h9 M17 6h3 M4 12h3 M11 12h9 M4 18h11 M19 18h1 M15 4v4 M9 10v4 M17 16v4` |
| `assistant.svg` | `M4 5h16v11H9l-5 4z M8 10h8 M8 13h5` |
| `cancel.svg` | `M6 6l12 12 M18 6L6 18` |
| `resume.svg` | `M5 4l10 8-10 8z M19 5v14` |
| `rollback.svg` | `M4 9h11a5 5 0 0 1 0 10H8 M4 9l4-4 M4 9l4 4` |
| `check.svg` | `M5 12l5 5 9-10` |
| `warning.svg` | `M12 3l10 18H2z M12 10v4 M12 17h.01` |
| `search.svg` | `M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z M20 20l-4-4` |

`desktop/icons.py`:
```python
"""Token-coloured SVG icons (no third-party packs). icon("play", role="primary") -> QIcon."""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from .styles import tokens

ICON_DIR = Path(__file__).parent / "assets" / "icons"
ROLE_COLOURS = {"primary": tokens.TEXT_PRIMARY, "secondary": tokens.TEXT_SECONDARY, "accent": tokens.ACCENT_HOVER,
                "success": tokens.ACCENT_SUCCESS, "warning": tokens.ACCENT_WARNING, "error": tokens.ACCENT_ERROR}

@lru_cache(maxsize=256)
def _pixmap(name: str, colour: str, size: int, dpr: float) -> QPixmap:
    svg = (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8").replace("currentColor", colour)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm

def icon(name: str, role: str = "secondary", size: int = 20) -> QIcon:
    dpr = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
    ic = QIcon()
    ic.addPixmap(_pixmap(name, ROLE_COLOURS[role], size, dpr), QIcon.Normal, QIcon.Off)
    ic.addPixmap(_pixmap(name, ROLE_COLOURS["accent"], size, dpr), QIcon.Normal, QIcon.On)
    ic.addPixmap(_pixmap(name, tokens.TEXT_SECONDARY, size, dpr), QIcon.Disabled, QIcon.Off)
    return ic
```
The light theme needs its own colours. Have `icon()` read the active palette from `styles` (light tokens mapped in
`dark_theme.py`), and clear the cache on theme switch (`_pixmap.cache_clear()`).
**Tests:** every file in the table exists and renders with non-zero alpha pixels (offscreen `QGuiApplication`; the
verification snippet used on 2026-10-31 rendered 638 non-transparent pixels for `home`).

---

## WI-4.2 Systems service (Qt-free core + Qt adapter)

`core/systems.py`:
```python
@dataclass(frozen=True)
class SystemRow:
    key: str            # "ollama" | "engine" | "editor" | "ram" | "disk" | "hosted"
    state: str          # "ok" | "degraded" | "offline" | "unknown"
    summary: str        # "4 models · 7.1 GB VRAM in use"
    fix_action: str | None = None   # "start_ollama" | "set_engine" | "open_hosted" | None

@dataclass(frozen=True)
class SystemsSnapshot:
    rows: tuple[SystemRow, ...]
    taken_at: float
    @property
    def overall(self) -> str: ...   # "ok" if all ok; "offline" if engine or ollama offline; else "degraded"

def probe_all(settings: Settings, timeout_s: float = 3.0) -> SystemsSnapshot: ...
```
- Ollama: `GET {ollama_url}/api/tags` (models) and `/api/ps` (`size_vram` sum), with a 3 s timeout.
- Engine: `settings.engine` present, and `UnrealEditor.exe` exists.
- Editor: link states from `GameTools._links` (offline if none).
- RAM: `psutil.virtual_memory().percent` (degraded > 85 %).
- Disk: `shutil.disk_usage(projects_root)` (degraded < 50 GB, offline < 20 GB).
- Hosted: `ModelRouter.attach_hosted` profiles that are enabled and opted in.

`desktop/services/systems_service.py`: a QObject that runs `probe_all` on the JobManager every 30 s while the window is
visible (120 s minimised), emits `snapshotChanged(object)`, and exposes `refresh_now()`. **This replaces**
`MainWindow._check_ollama_status`, and the existing toolbar status labels are removed in WI-4.3.

---

## WI-4.3 Shell: top bar, rail, view host, assistant panel, toasts

1. `shell/view_host.py`: `ViewHost(QStackedWidget)` with `register(view_id, factory, enabled_when)`. Views are created
   on the first `show_view(view_id)`. `view_id` values: `home games design build play evidence assets code settings`.
   It emits `viewChanged(str)`.
2. `shell/rail.py`: a `QWidget` with a vertical layout of `QToolButton`s (checkable, autoExclusive), icons from WI-4.1,
   tooltips "Label (Ctrl+N)", 56 px wide and a 3 px accent indicator (QSS `border-left`). Disabled items show the reason in
   the tooltip.
3. `shell/top_bar.py`: logo button, project switcher (`QComboBox` editable with a `QCompleter`), breadcrumb label,
   active-run chip (hidden unless a run is active, fed by `forge_service.runEvent`), Systems pill (opens a `QMenu`-style
   popover listing the `SystemRow`s with fix buttons), assistant toggle and palette button.
4. `shell/assistant_panel.py`: wraps the existing `ChatPanel` (moved, not rewritten). The model selector moves from the
   main toolbar into this header. The chat panel's internal header controls that duplicate it are removed.
5. `shell/toasts.py`: an overlay widget anchored bottom-right, with at most 3 toasts.
6. `main_window.py`: a new `_build_studio_shell()` used when `GAMEFORGE_LEGACY_SHELL` is not `"1"`. The old
   `_build_toolbar`, `_build_activity_rail` and `_build_docks` remain for the legacy path and for the Code view
   (`code_view.py` hosts the docks inside a nested `QMainWindow`. That is legal in Qt and keeps the dock behaviour).
   Persist splitter and assistant width in `.gameforge/ide_settings.ini` under new keys (`studio/assistant_width`,
   `studio/last_view`).
7. Shortcuts per the spec §2, registered with `QShortcut` on the main window. The palette (`shell/palette.py`) moves the
   existing palette code out of `main_window.py` and adds entries for every view and primary action.

**Tests (pytest-qt style with the existing `qapp` fixture):** the shell builds with `objectName`s; Ctrl+1…8 switch views;
disabled rail items do not switch; views are created lazily (count instantiations); the assistant toggle hides and
restores its width; the legacy flag yields the old layout and the old tests pass under it.

---

## WI-4.4 Home view

Per spec §4.1. The prompt box is a `QPlainTextEdit` (Enter = newline, Ctrl+Enter = Design it). Preset chips come from
`design.presets.PRESETS` titles. "Design it →" runs `prompt_to_gds` on the JobManager with `complete_json` from the
`design` role model. Then: `OK` → `design_view.open_draft(gds)`; `NEEDS_INPUT` → Design with questions;
`UNSUPPORTED` → an inline message "That doesn't look like a game request. Try the Assistant." Recent games come from
`projects_service` (top 6 by `updated_at`). Readiness comes from the systems service.

## WI-4.5 Games view
Per spec §4.2. `projects_service.list_games()` scans `settings.projects_root/*/GameForge/design/game.gds.json` and joins
`runs_index.json`. Thumbnail choice: the newest of `Saved/GameForge/evidence/**/*.png`, then
`Saved/GameForge/*.png`. It uses a `QAbstractListModel` and `QListView` in IconMode. Delete is a confirm dialog listing
the folders and requiring the typed game name, then `shutil.rmtree` on a job. If the project is open in an editor link,
the delete refuses.

## WI-4.6 Design view
Per spec §4.3.
- `widgets/gds_form.py`: builds the form from the pydantic model **by section with explicit widgets**. It is not
  fully generic: the GDS is fixed and hand-tuned forms read better. Overview (genre/camera combos, pitch,
  session minutes), World (levels table), Things (entities table: id, kind, count, module, placement summary; the
  row "⋯" opens a props editor whose fields come from the kit module params model in P5 and are raw key/values before
  that), Rules (sentence list + `rule_editor.py` structured dialog), Goals (two lists of condition sentences with
  add/edit), Look & sound, HUD & menus, Tech, Acceptance.
- Validation: debounce 300 ms → `GameDesignSpec.model_validate(draft_dict)` on the UI thread (it is fast: < 5 ms for
  typical specs; measure it, and move it to a job if > 20 ms). Map pydantic `loc` paths to widgets for inline errors.
- Save (Ctrl+S): `design.store.save` with revision+1. On `RevisionConflict` offer Reload.
- History: a dropdown of revisions → a diff dialog (a table of ops from `store.diff`).
- **Build game:** builds the Forge run (P1 legacy adapter today, the P6 composer later), shows the approval dialog with
  the scope, then starts it. It disables itself while a run is active for this project.
- Questions panel: answers write into the draft. "Yes/No" maps to explicit GDS changes that the generator records with
  each question (`prompt_to_gds` returns `questions` as plain strings in P1; P4 extends `PromptToGdsResult` with
  optional `suggested_patches: list[dict]` per question. Add that field and fill it only where the expander knows the
  patch, e.g. relic count).

## WI-4.7 Build view
Per spec §4.4. Timeline = `QListView` with `StepRowDelegate`. The log view is a `QPlainTextEdit` in read-only mode with
`setMaximumBlockCount(5000)` and batched appends every 100 ms. Problems come from step `data.diagnostics` (build),
automation failures and scenario failures. Actions: Cancel (`ForgeExecutor.request_cancel` through `forge_service`),
Resume (re-submit the run), Roll back (`ProjectRepo.reset_to`, refused while an editor link for the project is open).

## WI-4.8 Play view and WI-4.9 Evidence view
Per spec §4.5–4.6. The scenario table reads `ScenarioResult` files from the latest run's scenario step artifacts.
Evidence uses a gallery `QListView` (IconMode) over the artifacts of all runs of the project, plus a detail pane
(an image viewer with fit/zoom, a Markdown viewer and a JSON viewer).

## WI-4.10 Assets view, Code view, Settings view, onboarding
- Assets: `QTableView` over `AssetRegistry.search()`.
- Code: hosts the legacy docks (Explorer, Diff, Unreal, Terminal). The terminal is created on first show.
- Settings: sections per spec §4.9. Writes the user settings file (`core.settings.user_settings_path()`; create the
  folder) and calls `reset_settings_cache()`, then emits `settingsChanged` so services refresh.
- Onboarding: a `QWizard` with 3 pages per spec §4.10. It is shown when `user_settings_path()` does not exist or
  `get_settings().engine is None`.

## WI-4.11 Assistant routing
`AgentRuntime`'s game fast path (`runtime.py:427-444`) now returns a card payload `{"type": "open_design", "prompt": …}`
instead of creating a `create_game` approval. The assistant panel renders it as a card with **Open in Design**, which
calls Home's prompt flow with that prompt. Change requests on an open project ("make the guards faster") get the same
card type with `"mode": "change"`. P8 wires the patch path, and until then the card says "Edit the design to apply
this change". The `create_game` tool remains for the legacy shell and scripts only.

## WI-4.12 Quality gates
1. **UI stall detector** (`desktop/diagnostics/stall_monitor.py`): a 16 ms `QTimer` that measures lateness and records
   stalls > 50 ms with a Python stack sample (`sys._current_frames()` of the main thread). It is enabled by
   `GAMEFORGE_STALL_MONITOR=1` and writes `reports/P4/stalls.json`. Run the usability walk with it on. The gate is zero
   stalls > 50 ms after startup (startup excluded: measure it separately).
2. **DPI screenshots:** `scripts/ide/ide_snapshot.py --scale 1.0|1.25|1.5 --view <id>` (set
   `QT_SCALE_FACTOR` per run) → `reports/P4/dpi_<scale>_<view>.png` for all views. Check for clipping by hand and attach
   the notes.
3. **Contrast audit:** `scripts/ide/contrast_audit.py` computes WCAG ratios for every (text role, background role) pair
   in both themes and fails below 4.5.
4. **Resource benchmark:** `ide_resource_benchmark.py` with the new shell stays within budgets.
5. **Usability walk** (`tests/integration/test_studio_walk.py`, run manually): with fake Forge handlers that complete
   in 0.2 s each, type a prompt → Design shows the GDS → Build game → approve → Build timeline finishes → Play view lists
   fake scenario results → Evidence shows a fake screenshot. Every step is asserted by `objectName` lookups.

## WI-4.13 Remove the legacy shell
After the gates pass: delete `_build_toolbar`'s status widgets, the rail emoji actions, the dock tab strip code and the
`GAMEFORGE_LEGACY_SHELL` branch. Keep the Code view docks. Update tests that targeted removed widgets so they target the
new ones, and list each changed test in the commit message.

## Phase exit gate
1. All unit tests green, plus the usability walk.
2. Evidence: `reports/P4/` `stalls.json` (0 stalls > 50 ms), `dpi_*.png` (27 images: 9 views × 3 scales), contrast
   audit output, resource benchmark JSON within budget, and `studio_walk.mp4` *or* a numbered screenshot sequence of the
   walk.
3. A real end-to-end in the new UI: prompt "make a platformer with 6 coins" → Design → Build → PASS → Play launches the
   game (manual, recorded with screenshots).
4. Context, status and progress updated.

## Failure cases and prevention
- **Nested `QMainWindow` focus issues in the Code view:** set `setWindowFlags(Qt.Widget)` on the nested window and make
  sure shortcuts use `Qt.WindowShortcut` on the outer window.
- **Stale settings after a Settings change:** always call `reset_settings_cache()` and emit `settingsChanged`.
  Services re-read on that signal.
- **Long GDS forms slow to build:** build sections lazily when expanded.
- **Tests depending on removed widgets:** run the full suite after WI-4.13, not before.

## Progress
| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 4.1 | DONE | 2026-10-31T14:15Z | 2026-10-31T14:20Z | 16 SVGs in assets/icons/, desktop/icons.py with theme support, test_icons.py (4 passed) |
| 4.2 | DONE | 2026-10-31T14:20Z | 2026-10-31T14:30Z | core/systems.py (SystemRow, SystemsSnapshot, probe_all), desktop/services/systems_service.py (SystemsService), test_systems_service.py (3 passed), unit 631 passed |
| 4.3 | DONE | 2026-10-31T14:30Z | 2026-10-31T14:45Z | shell package (view_host, rail, top_bar, assistant_panel, toasts, palette), main_window._build_studio_shell, test_studio_shell.py (5 passed) |
| 4.4 | DONE | 2026-10-31T14:45Z | 2026-10-31T15:00Z | desktop/views/home_view.py, services/projects_service.py, test_home_view.py (7 passed), benchmark idle CPU 0.21% |
| 4.5 | DONE | 2026-10-31T15:00Z | 2026-10-31T15:15Z | desktop/views/games_view.py, GamesListModel, GameCardDelegate, DeleteGameDialog, test_games_view.py (5 passed) |
| 4.6 | DONE | 2026-10-31T15:15Z | 2026-10-31T15:35Z | desktop/views/design_view.py, widgets/gds_form.py, widgets/rule_editor.py, design/store load_revision, test_design_view.py (7 passed) |
| 4.7 | TODO | | | |
| 4.8–4.9 | TODO | | | |
| 4.10 | TODO | | | |
| 4.11 | TODO | | | |
| 4.12 | TODO | | | |
| 4.13 | TODO | | | |

## Review log (Claude)
_empty_

## Revisions
- 2026-10-31: created (Claude).
