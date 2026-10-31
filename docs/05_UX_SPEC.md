# GameForge Studio — UX Specification (v2)

**Owner:** Claude. **Created:** 2026-10-31. **Implements:** AD-18 in P4. **Supersedes:** roadmap §4b (the 7-step polish
pass, done 2026-10-31). That pass fixed defects but kept a code-IDE layout. This spec changes the information
architecture so that the product loop, *idea → design → build → play → change*, is the main path through the app.

---

## 1. Principles

1. **One obvious next step.** Every screen has at most one primary button (accent filled), and it is the next step of
   the loop.
2. **Evidence over claims.** A status is shown as PASS only with a link to its evidence. "Built" means packaged and its
   scenarios passed; otherwise the UI says exactly what is missing.
3. **Never block, always cancellable.** Every long action shows progress, elapsed time and a Cancel. The UI thread
   never waits on I/O (stall budget: 50 ms).
4. **Progressive disclosure.** Novices see the design summary, the build timeline and the Play button. Raw JSON, logs,
   code and the terminal are one click away and never in the way.
5. **Keyboard-complete and accessible.** Every action has a palette entry, every control has an accessible name, and
   text contrast is ≥ 4.5:1.
6. **Honest copy.** Plain verbs on buttons ("Build game", not "Execute pipeline"). Status words come from the evidence
   vocabulary (PASS / FAILED / BLOCKED / NOT VERIFIED).

## 2. Information architecture

```
┌ Top bar (48 px) ─────────────────────────────────────────────────────────────────────────────────────┐
│ ◆ GameForge │ [Project ▾ Platformer] › Design      ◉ Building Platformer · 4/8 · 03:12      ● Ready ▾ │ ✦ │ ⌘K │
├──────┬────────────────────────────────────────────────────────────────────────────────┬──────────────┤
│ Rail │                                Central view                                    │  Assistant   │
│ 56px │                      (QStackedWidget, lazily created)                          │  (360–480px, │
│ Home │                                                                                │  collapsible)│
│ Games│                                                                                │              │
│Design│                                                                                │              │
│ Build│                                                                                │              │
│ Play │                                                                                │              │
│Evid. │                                                                                │              │
│Assets│                                                                                │              │
│ ──── │                                                                                │              │
│ Code │                                                                                │              │
│Setts.│                                                                                │              │
├──────┴────────────────────────────────────────────────────────────────────────────────┴──────────────┤
│ Workspace: E:\GameForge\ide_ws                                                     GameForge 1.0.0-dev │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Rail item | Shortcut | Purpose | Enabled when |
|---|---|---|---|
| Home | Ctrl+1 | Start: prompt, presets, recent games, readiness | always |
| Games | Ctrl+2 | All games (projects): status, thumbnail, last run | always |
| Design | Ctrl+3 | The current game's GDS: summary, form editor, history | a project is selected |
| Build | Ctrl+4 | Runs: timeline, logs, problems, cancel/resume/rollback | always (lists all runs) |
| Play | Ctrl+5 | Launch the game; scenario results; captures | project has a package |
| Evidence | Ctrl+6 | Gallery of screenshots, reports, scenario results, provenance | project selected |
| Assets | Ctrl+7 | Asset registry browser (provenance, licence, previews) | always |
| Code | Ctrl+8 | Developer mode: explorer, diff review, terminal, Unreal panel (existing docks) | always |
| Settings | Ctrl+, | Engine, paths, models and providers, egress, storage, appearance | always |

Global: **Assistant** toggle Ctrl+J. **Command palette** Ctrl+K and Ctrl+Shift+P. **Cancel active run** Ctrl+. (with
confirmation). **Theme** Ctrl+T (unchanged).

Removed relative to today: the dock tab strip duplicating the rail; the "Check Ollama" toolbar button (moved into the
Systems popover); the model combo in the top bar (moved to the Assistant header and Settings); the permanent terminal
(Code view only); the static engine-install table (Systems popover and Settings).

## 3. Shell components

- **Top bar.** (1) Logo + product name, which opens Home. (2) Project switcher: an editable combo with search, listing
  the games under `projects_root`, plus "Open project folder…". (3) Breadcrumb with the current view name. (4) Active-run
  chip, visible only while a run is RUNNING or WAITING_APPROVAL: `◉ Building <game> · <done>/<total> · mm:ss`, amber
  when waiting for approval, and a click opens Build. (5) **Systems pill**: a coloured dot + word (`Ready`,
  `Degraded`, `Offline`) opening a popover with rows for Ollama (models loaded, VRAM from `/api/ps`), Unreal Engine
  (version, path), Editor link (offline/starting/idle/busy/PIE/crashed), RAM/CPU (psutil), Disk free on the projects
  drive, and Hosted providers (enabled/opted-in). Each row has a one-word state and a fix action ("Start Ollama",
  "Set engine path…"). (6) Assistant toggle. (7) Palette button.
- **Rail.** 56 px wide, vector icons (§7), tooltip with the label and shortcut, a 3 px accent bar on the active item, and
  a disabled state with a tooltip reason ("Select a game first").
- **Assistant panel.** The existing chat moves here. Header: model selector (roles from settings; hosted models are
  marked ☁), New chat and Clear. It is **context-aware**: when the user types a game-creation or change request, the
  assistant replies with a card "Open in Design" instead of starting builds itself (AD-11 single executor).
  Width is persisted and the panel collapses to 0.
- **Toasts.** Bottom-right, at most 3 stacked, auto-dismiss after 6 s unless they are errors. Every error toast has
  "Details" (opens the relevant view and step).

## 4. Views

### 4.1 Home
```
            Make a game
  ┌──────────────────────────────────────────────────────────────┐
  │ Describe your game… e.g. "a third-person forest adventure    │
  │ where I collect 5 relics while avoiding guards"              │
  └──────────────────────────────────────────────────────────────┘
   [ Tic-Tac-Toe ] [ Platformer ] [ Arena ] [ Card battler ] [ Explore a world ]      (preset chips)
                                                         [ Design it → ]  (primary)
  Recent games                                                     Readiness
  ┌────────┐ ┌────────┐ ┌────────┐                               ● Unreal Engine 5.7.4
  │ thumb  │ │ thumb  │ │ thumb  │                               ● Ollama · 4 models
  │Platfor.│ │TicTac..│ │Village │                               ● Disk 512 GB free
  │PASS 2h │ │FAIL 1d │ │ —      │                               ○ Hosted models: off  [Set up]
  └────────┘ └────────┘ └────────┘
```
- "Design it →" runs `prompt_to_gds` on a JobManager job. A spinner reads "Drafting a design…" (with Cancel). The
  result opens **Design**. If the result is `NEEDS_INPUT`, Design opens with the questions panel showing.
- Preset chips prefill the prompt box. They do not start anything.
- Readiness rows come from the same Systems service as the pill.

### 4.2 Games
A grid (or list, toggle) of game cards: thumbnail (latest scenario capture, else gameplay screenshot), title, genre,
last run status + time, GDS revision. Card actions: Open (→ Design), Play, Build, Show in Explorer, Delete… (a confirm
dialog that lists exactly which folders will be removed, and needs the user to type the game name). Sorting: recent and
name. Filter: status.

### 4.3 Design (the heart of the loop)
```
 Relic Run  ·  revision 3  ·  ✓ valid                  [History ▾]  [Raw JSON]   [ Build game ]
 ┌ Overview ──────────────────────────────┐ ┌ Questions (2) ─────────────────────────────┐
 │ Genre [Action adventure ▾] Camera [3rd]│ │ • Should guards end the game on sight?  [Yes][No]│
 │ Pitch [ ...                         ]  │ │ • How many relics? [5]                           │
 └────────────────────────────────────────┘ └────────────────────────────────────────────┘
 ┌ World ─────────────┐ ┌ Things in the game ──────────────────────────────────────────────┐
 │ Level 1 · forest   │ │ Player   1   kit.player_character   start                 [⋯]   │
 │ 150 × 150 m · dusk │ │ Relics   5   kit.pickup             scattered (min 8 m)   [⋯]   │
 │ seed 2026 [↻]      │ │ Guards   3   kit.guard              patrol                [⋯]   │
 └────────────────────┘ └──────────────────────────────────────────────────────────────────┘
 ┌ Rules ────────────────────────────────────────────────────────────────────────────────────┐
 │ When the player collects a relic → add 10 to score                                      [⋯] │
 │ When a guard spots the player → the player loses                                        [⋯] │
 ├ How to win / lose ────────────────────────────────────────────────────────────────────────┤
 │ Win: the player has collected 5 relics      Lose: a guard spots the player             │
 └───────────────────────────────────────────────────────────────────────────────────────────┘
 [ Look & sound ]  [ HUD & menus ]  [ Tech & budgets ]  [ Acceptance tests (4) ]      (collapsible sections)
```
- Every section is a card generated from the GDS. Enums are combos, numbers are spin boxes with the schema bounds, and
  lists are tables with add/remove/duplicate. Edits update an **in-memory draft** and are validated on change
  (debounced 300 ms). Invalid fields get a red underline and an inline message, and the header shows `✕ 2 problems`
  (click to jump to them).
- Rules and win/lose render as **sentences** (`design/render.py`). Editing a rule opens a structured editor:
  When [event ▾] (from [entity ▾]) / If [conditions…] / Then [effects…]. There is no free text, except `custom_code`
  descriptions, which show a badge "needs code generation".
- **Save** (Ctrl+S) writes a new revision. Unsaved changes show a dot on the tab and a prompt on navigation.
  **History** lists revisions with a diff view (old → new, using `store.diff`).
- **Build game** (primary): saves if needed, then shows the run approval dialog (scope: project folder, editor
  operations, packaging, estimated minutes) and starts the Forge run. It jumps to Build.
- **Questions** panel: shown when `prompt_to_gds` returned questions. Answers are applied as GDS edits.
- **Raw JSON**: a read-only by default code editor with a monospace font and validation. "Edit JSON" requires
  confirmation and validates before applying.
- **Acceptance tests** section: the scenario list with source (`derived from win[0]`), must-pass toggle, and gaps from
  the generator in amber ("Needs the rules engine (planned)").

### 4.4 Build
```
 Runs ▾ [Platformer · run_20261102_1412 · RUNNING]                     [Cancel] [Resume] [Roll back ▾]
 ┌ Timeline ────────────────────────────┐ ┌ Step: build_editor (attempt 1) ───────────────────────┐
 │ ✓ Design            0.1 s            │ │ Status RUNNING · 01:42 · engine lock held              │
 │ ✓ Scaffold          2.3 s   ⎘ ckpt   │ │ ┌ Log (live, last 5,000 lines) ─────────────── [⤓] ─┐ │
 │ ✓ Sources           0.4 s   ⎘ ckpt   │ │ │ [2/14] Compile GFPlatformerCharacter.cpp            │ │
 │ ◉ Build editor     01:42             │ │ │ ...                                                 │ │
 │ ○ Assemble level                     │ │ └────────────────────────────────────────────────────┘ │
 │ ○ Automation tests                   │ │ Problems (0)    Artifacts (1: build.log)               │
 │ ○ Package                            │ └────────────────────────────────────────────────────────┘
 │ ○ Scenarios (3)                      │
 └──────────────────────────────────────┘
```
- The timeline comes from Forge `RunState` and events (WI-2.8 `forge_service`). Icons: ✓ DONE, ◉ RUNNING, ○ PENDING,
  ✕ FAILED, ⊘ BLOCKED, ⏸ WAITING_APPROVAL, ↷ SKIPPED (skipped steps are dimmed with a tooltip "unchanged since run X").
- **Problems:** parsed diagnostics (UBT/UHT/automation/scenario failures) as a table: severity, file:line, message.
  Double-click opens the file in Code view at the line.
- **Roll back ▾** lists step checkpoints: "Return to after *Sources*". It is disabled while the editor is running
  (tooltip says why), and it needs confirmation listing the files that will change (`changed_since`).
- **Resume** is shown for FAILED, CANCELLED and interrupted runs. **Cancel** needs confirmation if the run is
  more than 30 s in.
- A finished run shows a summary banner: PASS → "Ready to play" with [Play], or FAILED → "Failed at <step>:
  <first error>" with [Show problem] and [Ask the assistant to fix] (P8).

### 4.5 Play
- A primary **Play** button (launches the packaged binary, detached, through `play_game`), with a configuration
  selector (Development / Shipping when both exist).
- A scenario results table: id, source, PASS/FAIL, duration, legs (count, any teleport/stuck), and a Details drawer
  (steps, expectations, captures).
- **Run scenarios again** (a Forge run with only scenario steps).
- Later (P10): "Record a scenario" from a play session.

### 4.6 Evidence
A filterable gallery: screenshots, scenario captures, reports (Markdown rendered), provenance records, packaged
artefacts with size and SHA-256. Each item shows its run and step. **Export report** produces a Markdown/HTML bundle into
`Saved/GameForge/exports/`.

### 4.7 Assets
The existing `AssetPanel` grows into a table view backed by the registry: name, type, stage, provenance class, licence,
backend, created, and a preview thumbnail. Filters by provenance and licence class. A detail drawer shows the lifecycle
events and evidence. Read-only in P4. Promote and quarantine actions come in P7.

### 4.8 Code (developer mode)
The current dock layout (Explorer, Diff review, Unreal panel, Terminal), restored exactly inside this view. The
terminal is created lazily when first shown. This is where the agent's code diffs are reviewed.

### 4.9 Settings
Sections: **Engine** (detected installs from `discover_engines()`, path override, Validate); **Paths** (projects
root, artifacts root); **Models** (role → model table, test button running the native tool self-test); **Hosted
providers** (existing dialog content, embedded); **Privacy & egress** (per-workspace opt-in list); **Storage** (caps,
cleanup preview); **Appearance** (theme, font scale 90–150 %). Writes go to the settings file through
`core/settings.py`, then `reset_settings_cache()`.

### 4.10 First-run onboarding (modal, 3 steps, skippable)
1. "Find Unreal Engine": auto-detected installs; pick one or browse. Validation shows the version.
2. "Choose where games are saved": default from settings; disk free shown; warn below 50 GB free.
3. "Models": Ollama detected? Lists local models, or offers "Start Ollama" / "Use a hosted provider…". A readiness
   summary follows. This is shown when the settings file is missing or the engine is not found.

## 5. States every view must handle

| State | Pattern |
|---|---|
| Loading | Skeleton rows (no spinner wheel for < 300 ms) |
| Empty | EmptyState card: icon, one sentence, primary action |
| Error | Inline banner with the error's first line, [Details], [Retry] |
| Offline dependency | Banner naming the dependency and the fix action (from the Systems service) |
| Long operation | Progress + elapsed + Cancel; a toast when it completes in the background |

## 6. Visual system (extends `desktop/styles/tokens.py`)

- **Spacing** 4/8/12/16/24 (add `SPACE_XL = 24` for page margins). **Radius** 6 (cards), 999 (pills).
- **Type** (Segoe UI Variable / Segoe UI): 11 caption, 13 body, 14 section title, 18 view title, 24 Home hero
  (`FONT_HERO = 24`, the only new size). Monospace: Cascadia Mono → Consolas.
- **Colour roles** (dark; light mapped in `dark_theme.py`): `BG_ROOT`, `BG_PANEL`, `BG_SURFACE`, `BG_HOVER`,
  `BG_ACTIVE`, `BORDER`, `BORDER_FOCUS`, `TEXT_PRIMARY`, `TEXT_SECONDARY`, `ACCENT_*`. Status colours are always paired
  with an icon or word, never colour alone.
- **Elevation:** no drop shadows. Use 1 px borders plus surface steps (`BG_PANEL` → `BG_SURFACE`).
- **Motion:** 120 ms ease-out for panel collapse and toasts only. Honour the "reduce motion" setting (Appearance)
  by disabling animations.

## 7. Icons

Monochrome stroke SVGs drawn for GameForge (24×24, `stroke="currentColor"`, width 1.75, round caps/joins, no fill),
stored in `src/gameforge_ide/desktop/assets/icons/`. No third-party icon packs, so there is no download or licence
question. They are rendered through `QSvgRenderer`, with `currentColor` substituted by the token colour per state and
device-pixel-ratio aware (the path data is in the P4 handover, WI-4.1). Emoji glyphs (current rail) are removed.

## 8. Accessibility checklist (P4 exit gate)

- Every interactive widget has `setAccessibleName` and a tooltip. Icons-only buttons get names like "Build game".
- Tab order follows visual order in each view. Focus rings use `BORDER_FOCUS`, 2 px.
- Contrast: body text ≥ 4.5:1 and large text ≥ 3:1 in both themes (`scripts/ide/contrast_audit.py` computes these from
  the tokens).
- Screens render without clipping at 100 / 125 / 150 % scaling (screenshots in `reports/P4/dpi_*.png`).
- All actions are reachable by keyboard: the palette lists every rail item, every primary action and every setting
  section.

## 9. Performance rules

- Views are created on first show. Hidden views stop their timers (`hideEvent`).
- Lists use `QAbstractItemModel` + `QListView`/`QTableView`, never a widget per row, for anything that can exceed 50 rows.
- The log view is a ring buffer of 5,000 lines appended in batches every 100 ms.
- Thumbnails are decoded off-thread and cached at 256 px in `.gameforge/cache/thumbs/` (LRU 200 MB).
- No polling faster than 1 s. Systems probes run every 30 s while visible, 120 s otherwise, and on demand.
- **Budgets** (unchanged): idle CPU < 1 %, cold start < 2.5 s, private RAM idle ≤ 300 MB, no UI stall > 50 ms.
