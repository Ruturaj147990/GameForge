"""Engine and Toolchain Discovery Layer for GameForge Benchmark."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import EngineDiscoveryResult


def discover_unreal_engine() -> EngineDiscoveryResult:
    """Discovers installed Unreal Engine installations on the local system."""
    # 1. Check explicit environment override
    custom_ue = os.environ.get("GAMEFORGE_UE_PATH") or os.environ.get("UNREAL_ENGINE_PATH")
    candidate_dirs: List[Path] = []
    if custom_ue:
        candidate_dirs.append(Path(custom_ue))

    # 2. Known local drives and standard install directories
    candidate_dirs.extend([
        Path(r"E:\UE\UE_5.7"),
        Path(r"C:\Program Files\Epic Games\UE_5.7"),
        Path(r"C:\Program Files\Epic Games\UE_5.6"),
        Path(r"C:\Program Files\Epic Games\UE_5.5"),
        Path(r"C:\Program Files\Epic Games\UE_5.4"),
        Path(r"D:\UE\UE_5.7"),
        Path(r"E:\UE\UE_5.6"),
    ])

    for ue_dir in candidate_dirs:
        if not ue_dir.is_dir():
            continue

        version_file = ue_dir / "Engine" / "Build" / "Build.version"
        editor_cmd = ue_dir / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"
        run_uat = ue_dir / "Engine" / "Build" / "BatchFiles" / "RunUAT.bat"

        if editor_cmd.is_file():
            version_str = "5.x"
            if version_file.is_file():
                try:
                    with version_file.open("r", encoding="utf-8") as vf:
                        v_json = json.load(vf)
                        version_str = (
                            f"{v_json.get('MajorVersion', 5)}.{v_json.get('MinorVersion', 0)}.{v_json.get('PatchVersion', 0)}"
                        )
                except Exception:
                    pass

            return EngineDiscoveryResult(
                engine_name="unreal",
                is_installed=True,
                version=version_str,
                executable_path=str(editor_cmd),
                build_toolchain_path=str(run_uat) if run_uat.is_file() else None,
                is_runnable=True,
                notes=f"Discovered native Unreal Engine at {ue_dir}",
            )

    return EngineDiscoveryResult(
        engine_name="unreal",
        is_installed=False,
        notes="Unreal Engine not found in default paths or environment variables.",
    )


def discover_unity_engine() -> EngineDiscoveryResult:
    """Discovers installed Unity Editor installations on the local system."""
    custom_unity = os.environ.get("GAMEFORGE_UNITY_PATH") or os.environ.get("UNITY_EDITOR_PATH")
    candidate_dirs: List[Path] = []
    if custom_unity:
        candidate_dirs.append(Path(custom_unity))

    # Standard Unity Hub / Unity paths
    candidate_dirs.extend([
        Path(r"C:\Program Files\Unity\Hub\Editor"),
        Path(r"C:\Program Files\Unity\Editor"),
        Path(r"E:\Unity\Hub\Editor"),
    ])

    # Search Hub editor directory if it exists
    hub_editors = Path(r"C:\Program Files\Unity\Hub\Editor")
    if hub_editors.is_dir():
        for sub in hub_editors.iterdir():
            candidate_dirs.append(sub)

    for u_dir in candidate_dirs:
        if not u_dir.is_dir():
            continue

        exe = u_dir / "Editor" / "Unity.exe"
        if not exe.is_file():
            exe = u_dir / "Unity.exe"

        if exe.is_file():
            return EngineDiscoveryResult(
                engine_name="unity",
                is_installed=True,
                version=u_dir.name,
                executable_path=str(exe),
                is_runnable=True,
                notes=f"Discovered native Unity Editor at {exe}",
            )

    return EngineDiscoveryResult(
        engine_name="unity",
        is_installed=False,
        notes="Unity Editor not installed in standard locations. Real-engine Unity tests will be marked UNVERIFIED.",
    )


def discover_toolchains() -> Dict[str, Any]:
    """Inspects available development compilers, runtimes, and build tools."""
    results: Dict[str, Any] = {
        "python": sys.version.split()[0],
        "dotnet": None,
        "msbuild": None,
        "msvc": None,
        "git": None,
    }

    # Dotnet
    dotnet_bin = shutil.which("dotnet")
    if dotnet_bin:
        try:
            res = subprocess.run(["dotnet", "--version"], capture_output=True, text=True, timeout=5)
            results["dotnet"] = res.stdout.strip()
        except Exception:
            results["dotnet"] = "installed (version check timeout)"

    # MSBuild
    vs_msbuild = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe")
    if vs_msbuild.is_file():
        results["msbuild"] = str(vs_msbuild)
    elif shutil.which("msbuild"):
        results["msbuild"] = shutil.which("msbuild")

    # MSVC
    msvc_dir = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC")
    if msvc_dir.is_dir():
        versions = [p.name for p in msvc_dir.iterdir() if p.is_dir()]
        results["msvc"] = versions[-1] if versions else "detected"

    # Git
    git_bin = shutil.which("git")
    if git_bin:
        try:
            res = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
            results["git"] = res.stdout.strip()
        except Exception:
            results["git"] = "installed"

    return results


def discover_environment() -> Dict[str, Any]:
    """Assembles complete engine and toolchain discovery report."""
    ue = discover_unreal_engine()
    unity = discover_unity_engine()
    tools = discover_toolchains()

    return {
        "engines": {
            "unreal": {
                "is_installed": ue.is_installed,
                "version": ue.version,
                "executable_path": ue.executable_path,
                "build_toolchain_path": ue.build_toolchain_path,
                "is_runnable": ue.is_runnable,
                "notes": ue.notes,
            },
            "unity": {
                "is_installed": unity.is_installed,
                "version": unity.version,
                "executable_path": unity.executable_path,
                "is_runnable": unity.is_runnable,
                "notes": unity.notes,
            },
        },
        "toolchains": tools,
    }
