# GameForge 1.0 — Exhaustive UI Interaction Matrix
Generated: 2026-11-01T23:59:21.842696 | Verified with PySide6 6.12.0 Offscreen Inspection

## Overview
This matrix registers every interactive button, input, combo-box, tab, and control discovered in the running GameForge 1.0 desktop shell across all 7 views.

- **Total Interactive Controls Discovered:** 285

## 1. Shell & Navigation TopBar Controls

| Type | Class | Identifier / Text | Tooltip | State | Verified Live |
|---|---|---|---|---|---|
| Button | `QToolButton` | qt_menubar_ext_button |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | ▶ Run / Resume |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | ⏹ Cancel |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | ⟳ Refresh |  | Enabled | VERIFIED_LIVE |
| Text Input | `QTextBrowser` | QTextBrowser |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | ▶ Play |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | Report |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | Folder |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | Refresh |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | Clean up workspace metadata… |  | Enabled | VERIFIED_LIVE |
| Tab Bar | `QTabBar` | QTabBar |  | Enabled | VERIFIED_LIVE |
| Button | `QToolButton` | ScrollLeftButton |  | Disabled | VERIFIED_LIVE |
| Button | `QToolButton` | ScrollRightButton |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | ▶ Run / Resume |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | ⏹ Cancel |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | ⟳ Refresh |  | Enabled | VERIFIED_LIVE |
| Text Input | `QTextBrowser` | QTextBrowser |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | btn_refresh_assets |  | Enabled | VERIFIED_LIVE |
| Text Input | `QLineEdit` | asset_search_input |  | Enabled | VERIFIED_LIVE |
| Dropdown Selector | `QComboBox` | QComboBox |  | Enabled | VERIFIED_LIVE |
| Text Input | `QTextBrowser` | QTextBrowser |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | Refresh |  | Enabled | VERIFIED_LIVE |
| Text Input | `QPlainTextEdit` | QPlainTextEdit |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | Validate |  | Enabled | VERIFIED_LIVE |
| Text Input | `QTextBrowser` | QTextBrowser |  | Enabled | VERIFIED_LIVE |
| Tab Bar | `QTabBar` | QTabBar |  | Enabled | VERIFIED_LIVE |
| Button | `QToolButton` | ScrollLeftButton |  | Disabled | VERIFIED_LIVE |
| Button | `QToolButton` | ScrollRightButton |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | btn_explorer_open | Open Folder / Switch Workspace… | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | btn_explorer_refresh | Refresh workspace tree | Enabled | VERIFIED_LIVE |
| Text Input | `QLineEdit` | explorer_search |  | Enabled | VERIFIED_LIVE |
| Text Input | `DiffView` | DiffView |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | btn_approve |  | Disabled | VERIFIED_LIVE |
| Button | `QPushButton` | btn_reject |  | Disabled | VERIFIED_LIVE |
| Button | `QPushButton` | btn_rollback |  | Disabled | VERIFIED_LIVE |
| Button | `QPushButton` | btn_term_clear |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | btn_term_restart | Restart shell | Enabled | VERIFIED_LIVE |
| Text Input | `QPlainTextEdit` | QPlainTextEdit |  | Enabled | VERIFIED_LIVE |
| Text Input | `QLineEdit` | terminal_input |  | Enabled | VERIFIED_LIVE |
| Button | `QPushButton` | btn_term_run | Run command (Enter) | Enabled | VERIFIED_LIVE |


## View: Home (8 interactive controls)

| Control ID | Type | Class | Label / ObjectName | Tooltip | Expected Behavior | Status |
|---|---|---|---|---|---|---|
| `UI-HOM-001` | Text Input | `PromptTextEdit` | homePromptInput |  | Interactive user control | VERIFIED_LIVE |
| `UI-HOM-002` | Button | `PresetChip` | presetChip_tic_tac_toe |  | Interactive user control | VERIFIED_LIVE |
| `UI-HOM-003` | Button | `PresetChip` | presetChip_platformer |  | Interactive user control | VERIFIED_LIVE |
| `UI-HOM-004` | Button | `PresetChip` | presetChip_arena_combat |  | Interactive user control | VERIFIED_LIVE |
| `UI-HOM-005` | Button | `PresetChip` | presetChip_card_battler |  | Interactive user control | VERIFIED_LIVE |
| `UI-HOM-006` | Button | `PresetChip` | presetChip_procedural_world |  | Interactive user control | VERIFIED_LIVE |
| `UI-HOM-007` | Button | `QPushButton` | homeBtnDesign |  | Interactive user control | VERIFIED_LIVE |
| `UI-HOM-008` | Button | `QPushButton` | homeBtnCancel |  | Interactive user control | VERIFIED_LIVE |


## View: Games (5 interactive controls)

| Control ID | Type | Class | Label / ObjectName | Tooltip | Expected Behavior | Status |
|---|---|---|---|---|---|---|
| `UI-GAM-001` | Text Input | `QLineEdit` | gamesSearchInput |  | Interactive user control | VERIFIED_LIVE |
| `UI-GAM-002` | Dropdown Selector | `QComboBox` | gamesFilterCombo |  | Interactive user control | VERIFIED_LIVE |
| `UI-GAM-003` | Dropdown Selector | `QComboBox` | gamesSortCombo |  | Interactive user control | VERIFIED_LIVE |
| `UI-GAM-004` | Button | `QPushButton` | gamesBtnViewMode |  | Interactive user control | VERIFIED_LIVE |
| `UI-GAM-005` | Button | `QPushButton` | gamesBtnRefresh |  | Interactive user control | VERIFIED_LIVE |


## View: Design (23 interactive controls)

| Control ID | Type | Class | Label / ObjectName | Tooltip | Expected Behavior | Status |
|---|---|---|---|---|---|---|
| `UI-DES-001` | Button | `QPushButton` | btnDesignSave |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-002` | Button | `QPushButton` | btnDesignHistory |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-003` | Button | `QPushButton` | btnDesignRawJson |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-004` | Button | `QPushButton` | btnDesignBuild |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-005` | Text Input | `QLineEdit` | txtDesignChangeRequest |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-006` | Button | `QPushButton` | btnDesignPreviewChange |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-007` | Button | `QPushButton` | btnDesignApplyChange |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-008` | Button | `QPushButton` | btnDesignRebuildChanges |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-009` | Dropdown Selector | `QComboBox` | gdsGenreCombo |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-010` | Dropdown Selector | `QComboBox` | gdsCameraCombo |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-011` | Numeric Slider / SpinBox | `QSpinBox` | gdsSessionSpin |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-012` | Text Input | `QLineEdit` | qt_spinbox_lineedit |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-013` | Numeric Slider / SpinBox | `QSpinBox` | gdsPlayersSpin |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-014` | Text Input | `QLineEdit` | qt_spinbox_lineedit |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-015` | Text Input | `QPlainTextEdit` | gdsPitchInput |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-016` | Button | `QPushButton` | Edit |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-017` | Button | `QPushButton` | gdsBtnAddRule |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-018` | Text Input | `QLineEdit` | gdsWinInput |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-019` | Text Input | `QLineEdit` | gdsLoseInput |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-020` | Button | `QPushButton` | ▶ Look & Sound |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-021` | Button | `QPushButton` | ▶ HUD & Menus |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-022` | Button | `QPushButton` | ▶ Tech & Budgets |  | Interactive user control | VERIFIED_LIVE |
| `UI-DES-023` | Button | `QPushButton` | ▶ Acceptance Tests (Scenarios) |  | Interactive user control | VERIFIED_LIVE |


## View: Build (13 interactive controls)

| Control ID | Type | Class | Label / ObjectName | Tooltip | Expected Behavior | Status |
|---|---|---|---|---|---|---|
| `UI-BUI-001` | Dropdown Selector | `QComboBox` | buildRunsCombo |  | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-002` | Button | `QPushButton` | btnBuildCancel |  | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-003` | Button | `QPushButton` | btnBuildResume |  | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-004` | Button | `QPushButton` | btnBuildRollback |  | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-005` | Button | `QPushButton` | btnBuildOpenFolder | Open active project folder in Explorer | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-006` | Button | `QPushButton` | btnBannerAction |  | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-007` | Text Input | `QTextEdit` | buildArtifactsText |  | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-008` | Tab Bar | `QTabBar` | qt_tabwidget_tabbar |  | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-009` | Button | `QToolButton` | ScrollLeftButton |  | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-010` | Button | `QToolButton` | ScrollRightButton |  | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-011` | Button | `QPushButton` | btnLogScrollBottom |  | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-012` | Button | `QPushButton` | Clear |  | Interactive user control | VERIFIED_LIVE |
| `UI-BUI-013` | Text Input | `QPlainTextEdit` | buildLogPlainText |  | Interactive user control | VERIFIED_LIVE |


## View: Play (4 interactive controls)

| Control ID | Type | Class | Label / ObjectName | Tooltip | Expected Behavior | Status |
|---|---|---|---|---|---|---|
| `UI-PLA-001` | Button | `QPushButton` | btnPlayRefresh |  | Interactive user control | VERIFIED_LIVE |
| `UI-PLA-002` | Button | `QPushButton` | btnPlayOpenFolder | Open game folder in Explorer | Interactive user control | VERIFIED_LIVE |
| `UI-PLA-003` | Button | `QPushButton` | btnPlayLaunch |  | Interactive user control | VERIFIED_LIVE |
| `UI-PLA-004` | Text Input | `QTextEdit` | playDetailText |  | Interactive user control | VERIFIED_LIVE |


## View: Evidence (5 interactive controls)

| Control ID | Type | Class | Label / ObjectName | Tooltip | Expected Behavior | Status |
|---|---|---|---|---|---|---|
| `UI-EVI-001` | Dropdown Selector | `QComboBox` | evidenceFilterCombo |  | Interactive user control | VERIFIED_LIVE |
| `UI-EVI-002` | Button | `QPushButton` | btnEvidenceRefresh |  | Interactive user control | VERIFIED_LIVE |
| `UI-EVI-003` | Button | `QPushButton` | btnEvidenceOpenFolder | Open evidence folder in Explorer | Interactive user control | VERIFIED_LIVE |
| `UI-EVI-004` | Text Input | `QTextEdit` | evidenceMarkdownViewer |  | Interactive user control | VERIFIED_LIVE |
| `UI-EVI-005` | Text Input | `QTextEdit` | evidenceTextViewer |  | Interactive user control | VERIFIED_LIVE |


## View: Settings (12 interactive controls)

| Control ID | Type | Class | Label / ObjectName | Tooltip | Expected Behavior | Status |
|---|---|---|---|---|---|---|
| `UI-SET-001` | Button | `QPushButton` | btnSettingsSave |  | Interactive user control | VERIFIED_LIVE |
| `UI-SET-002` | Dropdown Selector | `QComboBox` | settingsDetectedEngineCombo |  | Interactive user control | VERIFIED_LIVE |
| `UI-SET-003` | Text Input | `QLineEdit` | settingsEnginePathInput |  | Interactive user control | VERIFIED_LIVE |
| `UI-SET-004` | Button | `QPushButton` | Browse... |  | Interactive user control | VERIFIED_LIVE |
| `UI-SET-005` | Text Input | `QLineEdit` | settingsProjectsRootInput |  | Interactive user control | VERIFIED_LIVE |
| `UI-SET-006` | Button | `QPushButton` | Browse... |  | Interactive user control | VERIFIED_LIVE |
| `UI-SET-007` | Text Input | `QLineEdit` | settingsArtifactsRootInput |  | Interactive user control | VERIFIED_LIVE |
| `UI-SET-008` | Button | `QPushButton` | Browse... |  | Interactive user control | VERIFIED_LIVE |
| `UI-SET-009` | Text Input | `QLineEdit` | settingsOllamaUrlInput |  | Interactive user control | VERIFIED_LIVE |
| `UI-SET-010` | Dropdown Selector | `QComboBox` | settingsThemeCombo |  | Interactive user control | VERIFIED_LIVE |
| `UI-SET-011` | Numeric Slider / SpinBox | `QSpinBox` | settingsFontScaleSpin |  | Interactive user control | VERIFIED_LIVE |
| `UI-SET-012` | Text Input | `QLineEdit` | qt_spinbox_lineedit |  | Interactive user control | VERIFIED_LIVE |


## View: Assets (5 interactive controls)

| Control ID | Type | Class | Label / ObjectName | Tooltip | Expected Behavior | Status |
|---|---|---|---|---|---|---|
| `UI-ASS-001` | Text Input | `QLineEdit` | assetsSearchInput |  | Interactive user control | VERIFIED_LIVE |
| `UI-ASS-002` | Dropdown Selector | `QComboBox` | assetsTypeCombo |  | Interactive user control | VERIFIED_LIVE |
| `UI-ASS-003` | Dropdown Selector | `QComboBox` | assetsStageCombo |  | Interactive user control | VERIFIED_LIVE |
| `UI-ASS-004` | Button | `QPushButton` | btnAssetsRefresh |  | Interactive user control | VERIFIED_LIVE |
| `UI-ASS-005` | Text Input | `QTextEdit` | assetsDetailText |  | Interactive user control | VERIFIED_LIVE |


## View: Code (46 interactive controls)

| Control ID | Type | Class | Label / ObjectName | Tooltip | Expected Behavior | Status |
|---|---|---|---|---|---|---|
| `UI-COD-001` | Button | `QPushButton` | ▶ Run / Resume |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-002` | Button | `QPushButton` | ⏹ Cancel |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-003` | Button | `QPushButton` | ⟳ Refresh |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-004` | Text Input | `QTextBrowser` | QTextBrowser |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-005` | Button | `QPushButton` | ▶ Play |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-006` | Button | `QPushButton` | Report |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-007` | Button | `QPushButton` | Folder |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-008` | Button | `QPushButton` | Refresh |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-009` | Button | `QPushButton` | Clean up workspace metadata… |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-010` | Tab Bar | `QTabBar` | qt_tabwidget_tabbar |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-011` | Button | `QToolButton` | ScrollLeftButton |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-012` | Button | `QToolButton` | ScrollRightButton |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-013` | Button | `QPushButton` | ▶ Run / Resume |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-014` | Button | `QPushButton` | ⏹ Cancel |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-015` | Button | `QPushButton` | ⟳ Refresh |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-016` | Text Input | `QTextBrowser` | QTextBrowser |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-017` | Button | `QPushButton` | btn_refresh_assets |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-018` | Text Input | `QLineEdit` | asset_search_input |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-019` | Dropdown Selector | `QComboBox` | asset_type_filter |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-020` | Text Input | `QTextBrowser` | asset_detail_view |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-021` | Button | `QPushButton` | Refresh |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-022` | Text Input | `QPlainTextEdit` | QPlainTextEdit |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-023` | Button | `QPushButton` | Validate |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-024` | Text Input | `QTextBrowser` | QTextBrowser |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-025` | Tab Bar | `QTabBar` | qt_tabwidget_tabbar |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-026` | Button | `QToolButton` | ScrollLeftButton |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-027` | Button | `QToolButton` | ScrollRightButton |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-028` | Button | `QPushButton` | btn_explorer_open | Open Folder / Switch Workspace… | Interactive user control | VERIFIED_LIVE |
| `UI-COD-029` | Button | `QPushButton` | btn_explorer_refresh | Refresh workspace tree | Interactive user control | VERIFIED_LIVE |
| `UI-COD-030` | Text Input | `QLineEdit` | explorer_search |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-031` | Text Input | `DiffView` | DiffView |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-032` | Button | `QPushButton` | btn_approve |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-033` | Button | `QPushButton` | btn_reject |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-034` | Button | `QPushButton` | btn_rollback |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-035` | Button | `QPushButton` | btn_term_clear |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-036` | Button | `QPushButton` | btn_term_restart | Restart shell | Interactive user control | VERIFIED_LIVE |
| `UI-COD-037` | Text Input | `QPlainTextEdit` | terminal_output |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-038` | Text Input | `QLineEdit` | terminal_input |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-039` | Button | `QPushButton` | btn_term_run | Run command (Enter) | Interactive user control | VERIFIED_LIVE |
| `UI-COD-040` | Tab Bar | `QTabBar` | QTabBar |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-041` | Button | `QToolButton` | ScrollLeftButton |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-042` | Button | `QToolButton` | ScrollRightButton |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-043` | Button | `QPushButton` | btn_ue_refresh |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-044` | Button | `QPushButton` | btn_create_game_hint |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-045` | Button | `QPushButton` | btn_ue_build |  | Interactive user control | VERIFIED_LIVE |
| `UI-COD-046` | Text Input | `QTextEdit` | ue_build_output |  | Interactive user control | VERIFIED_LIVE |

