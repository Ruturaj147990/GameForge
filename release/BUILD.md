# GameForge 1.0 — Distribution Build Guide

## 1. Portable Distribution (Standard)

The standard portable distribution bundles the complete GameForge application, including:
- PySide6 native IDE desktop package (`gameforge_ide`)
- Unreal Engine op catalog and content op library (`gameforge_ops`)
- Built Unreal Engine runtime/editor plugin binaries (`Plugins/GameForge`)
- One-click launcher (`GameForge.bat`)
- Non-admin user installer script (`Install-GameForge.ps1`)
- Application icon (`gameforge.ico`)

### Build Command:
```powershell
python scripts/pipeline/build_portable_distribution.py
```
Outputs:
- Directory: `E:\GameForge\release\GameForge-1.0.0-win64\`
- Archive: `E:\GameForge\release\GameForge-1.0.0-win64.zip`
- Verification: footprint <= 250 MB (excluding models, datasets, and engine).

---

## 2. Standalone Binary Compilation (Nuitka)

*Note: Requires user approval before installing Nuitka and zstandard compiler tools.*

```powershell
python -m pip install nuitka zstandard
python -m nuitka --standalone --plugin-enable=pyside6 `
  --include-package-data=src.gameforge_ide `
  --include-data-dir=src/gameforge_ide/desktop/assets=gameforge_ide/desktop/assets `
  --include-data-dir=src/gameforge_ide/config=gameforge_ide/config `
  --include-data-dir=src/gameforge_ide/unreal/GameForge=gameforge_ide/unreal/GameForge `
  --windows-icon-from-ico=release/gameforge.ico `
  --output-dir=E:\GameForge\release\nuitka `
  src/gameforge_ide/launcher.py
```
