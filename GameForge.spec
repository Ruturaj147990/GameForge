# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller Spec File for GameForge IDE Standalone Desktop Distribution.

Conforms to Master Transformation & Standalone Packaging Directive:
- Generates onedir directory distribution containing standalone GameForge.exe
- Strictly excludes heavy model weights, Ollama blobs, and protected benchmark graders
- Includes all runtime config, assets, and Unreal plugin templates
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Hidden imports covering backend, desktop, unreal, forge, and PySide6
hidden_imports = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'fastapi',
    'uvicorn',
    'pydantic',
    'pydantic_core',
    'src.gameforge_ide.launcher',
] + collect_submodules('src.gameforge_ide')

# Data files to bundle: config, schemas, templates, plugin sources
datas = [
    ('src/gameforge_ide/config', 'src/gameforge_ide/config'),
    ('src/gameforge_ide/unreal/GameForge', 'src/gameforge_ide/unreal/GameForge'),
]

a = Analysis(
    ['entrypoint.py'],
    pathex=['.'],
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
    name='GameForgeIDE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='GameForgeIDE',
)
