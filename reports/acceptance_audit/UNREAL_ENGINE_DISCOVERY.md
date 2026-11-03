# GameForge 1.0 — Automatic Unreal Engine Discovery & Validation Architecture

**Date:** 2026-11-02T08:12:00Z  
**Author:** Antigravity Autonomous Systems Engineer  
**Status:** IMPLEMENTED & VERIFIED (8/8 unit tests pass)

---

## 1. Architectural Requirement & Problem Statement

Previously, GameForge fell back to a hardcoded engine path (`E:\UE\UE_5.7`) in `src/gameforge_ide/core/settings.py` when detection via `LauncherInstalled.dat` yielded no hits. On systems where:
- Unreal Engine was installed on another drive (e.g. `C:\Program Files\Epic Games\UE_5.7` or `D:\UE\UE_5.7`), or
- Epic Games Launcher registered installs in modern `*.item` manifest files rather than legacy `.dat` files,
the IDE would fail to resolve the engine root, leading to fatal build and live editor connection failures.

---

## 2. Multi-Source Discovery Pipeline

GameForge 1.0 implements a dedicated, robust discovery subsystem in `src/gameforge_ide/unreal/discovery.py`. It probes five distinct sources in priority order:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       UNREAL ENGINE DISCOVERY PIPELINE                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Explicit Environment Overrides                                           │
│    GAMEFORGE_ENGINE_ROOT, UE_ENGINE_PATH, UNREAL_ENGINE_PATH                │
│                                                                             │
│ 2. Epic Games Launcher Manifest Items                                       │
│    %PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests\*.item               │
│                                                                             │
│ 3. Epic Games Launcher Database                                             │
│    %PROGRAMDATA%\Epic\UnrealEngineLauncher\LauncherInstalled.dat            │
│                                                                             │
│ 4. Windows Registry Scan (64-bit & 32-bit hives)                            │
│    HKLM & HKCU: SOFTWARE\EpicGames\Unreal Engine                            │
│    HKCU: SOFTWARE\Epic Games\Unreal Engine\Builds                           │
│                                                                             │
│ 5. Active Drive Filesystem Probing                                          │
│    [Drive]:\UE\UE_*                                                         │
│    [Drive]:\Program Files\Epic Games\UE_*                                   │
│    [Drive]:\Epic Games\UE_*                                                 │
│    [Drive]:\UnrealEngine\UE_*                                               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Candidate Path
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RIGOROUS VALIDATION GATE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ • Parse Engine/Build/Build.version -> Version (e.g. 5.7.4), Changelist      │
│ • Verify Engine/Binaries/Win64/UnrealEditor.exe exists                      │
│ • Locate UnrealBuildTool (.dll in DotNET/UnrealBuildTool or .exe)           │
│ • Verify PythonScriptPlugin remote_execution.py exists                      │
│ • Check version compatibility against target pinned minor (default 5.7.x)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Discovered Installation Details on Test PC

Executing `discover_all_engines()` on the current host yields:

- **Root Directory:** `E:\UE\UE_5.7`
- **Engine Version:** `5.7.4`
- **Changelist:** `51494982`
- **Branch:** `++UE5/Release-5.7`
- **Discovery Source:** `epic_manifest_item` (read from `C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests\1851B3264877EF59EAB0A480C9A1E40E.item`)
- **Editor Executable:** `E:\UE\UE_5.7\Engine\Binaries\Win64\UnrealEditor.exe` (VERIFIED PRESENT)
- **UnrealBuildTool:** `E:\UE\UE_5.7\Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.dll` (VERIFIED PRESENT)
- **Remote Execution Protocol:** `E:\UE\UE_5.7\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python\remote_execution.py` (VERIFIED PRESENT)
- **Compatibility Status:** `True` (matches pinned target `5.7`)

---

## 4. Diagnostics & Fail-Safe Behavior

If no compatible Unreal Engine installation is found:
1. `discover_all_engines()` collects and returns all candidates with clear diagnostics (e.g. `Version 5.6.2 differs from target 5.7.x`, `UnrealEditor.exe not found`).
2. `get_best_engine()` falls back to highest valid changelist version if pinned version is absent.
3. If no engine exists on the host, `EngineNotFoundError` provides actionable diagnostic instructions:
   ```text
   EngineNotFoundError: Unreal Engine 5.7 was not found. 
   Install Unreal Engine via Epic Games Launcher or set GAMEFORGE_ENGINE_ROOT in Settings.
   ```
4. User can configure or override the engine root path at any time via IDE Settings (`SettingsView` -> `Engine Root`).

---

## 5. Verification Test Suite

All 8 tests in `tests/unit/test_unreal_discovery.py` pass:
- `test_parse_engine_version_valid`: Validates parsing of `Build.version` triples and changelists.
- `test_parse_engine_version_missing`: Validates graceful `None` on missing files.
- `test_validate_engine_root_complete`: Full validation of complete engine installation.
- `test_validate_engine_root_missing_editor`: Diagnostics emitted when editor executable is missing.
- `test_validate_engine_root_incompatible_version`: Compatibility flag correctly evaluated.
- `test_scan_manifest_items`: Mocked scan of Epic Games Launcher `*.item` files.
- `test_scan_launcher_installed_dat`: Mocked scan of `LauncherInstalled.dat`.
- `test_discover_and_get_best_engine`: Precedence order and explicit override selection.
