# -*- mode: python ; coding: utf-8 -*-
"""GameForge IDE — PyInstaller Build Specification.

Bundles the native PySide6 desktop IDE into a standalone Windows executable.
Excludes the 16.8 GB GGUF model weights; connects to local Ollama on loopback.
"""

from pathlib import Path

block_cipher = None
REPO_ROOT = Path(r"E:\gameforge_step1").resolve()

a = Analysis(
    [str(REPO_ROOT / "src" / "gameforge_ide" / "launcher.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[
        (str(REPO_ROOT / "configs" / "engine_knowledge_registry.json"), "configs"),
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "fastapi",
        "uvicorn",
        "pydantic",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "torch",
        "scipy",
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
    name="GameForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed GUI mode
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="GameForge",
)
