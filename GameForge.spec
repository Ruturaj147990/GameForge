# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller Spec File for GameForge IDE Standalone Desktop Distribution.

Conforms to Master Transformation & Standalone Packaging Directive:
- Generates onedir directory distribution containing standalone GameForgeIDE.exe
- Strictly excludes heavy model weights, Ollama blobs, and protected benchmark graders
- Includes all runtime config, schemas, assets, and Unreal plugin templates
"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Hidden imports covering backend, desktop, unreal, forge, and PySide6
hidden_imports = (
    [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtSvg",
        "fastapi",
        "uvicorn",
        "pydantic",
        "pydantic_core",
        "src.gameforge_ide.launcher",
    ]
    + collect_submodules("src.gameforge_ide")
    + collect_submodules("src.gameforge_bench")
)

# Data files to bundle: config, schemas, templates, plugin sources, and SVG icons
datas = [
    ("configs", "configs"),
    ("schemas", "schemas"),
    ("src/gameforge_ide/config", "src/gameforge_ide/config"),
    ("src/gameforge_ide/unreal/GameForge", "src/gameforge_ide/unreal/GameForge"),
    ("src/gameforge_ide/desktop/assets/icons", "src/gameforge_ide/desktop/assets/icons"),
]

icon_path = Path("release/gameforge.ico")
exe_icon = str(icon_path) if icon_path.exists() else None

a = Analysis(
    ["entrypoint.py"],
    pathex=[".", "src"],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'graders',
        'models',
        'tests',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GameForgeIDE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=exe_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GameForgeIDE",
)
