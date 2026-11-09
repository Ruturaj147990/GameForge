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


def _load_host_profile_paths() -> Dict[str, str]:
    """Resolves host profile paths if GAMEFORGE_HOST_PROFILE or a host profile JSON exists."""
    repo_root = Path(__file__).resolve().parents[3]
    profile_name = os.environ.get("GAMEFORGE_HOST_PROFILE", "dev-rx7700xt")
    profile_path = Path(profile_name)
    if not profile_path.is_file():
        profile_path = repo_root / "configs" / "host_profiles" / f"{profile_name}.json"
    if profile_path.is_file():
        try:
            return json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def discover_unreal_engine() -> EngineDiscoveryResult:
    """Discovers installed Unreal Engine installations on the local system."""
    repo_root = Path(__file__).resolve().parents[3]
    custom_ue = os.environ.get("GAMEFORGE_UE_PATH") or os.environ.get("UNREAL_ENGINE_PATH") or os.environ.get("GAMEFORGE_UNREAL_ENGINE_ROOT")
    candidate_dirs: List[Path] = []
    if custom_ue:
        candidate_dirs.append(Path(custom_ue))

    profile = _load_host_profile_paths()
    if profile.get("unreal_engine_root"):
        candidate_dirs.append(Path(profile["unreal_engine_root"]))
    if profile.get("engine_root"):
        candidate_dirs.append(Path(profile["engine_root"]))

    # Also check configs/engine.json
    engine_json = repo_root / "configs" / "engine.json"
    if engine_json.is_file():
        try:
            ej = json.loads(engine_json.read_text(encoding="utf-8"))
            if ej.get("engine_root"):
                candidate_dirs.append(Path(ej["engine_root"]))
        except Exception:
            pass

    # Delegate to gameforge_ide discovery if available
    try:
        from src.gameforge_ide.unreal.discovery import discover_all_engines
        for inst in discover_all_engines():
            inst_root = Path(inst.root) if not isinstance(inst.root, Path) else inst.root
            if inst_root not in candidate_dirs:
                candidate_dirs.append(inst_root)
    except Exception:
        try:
            from gameforge_ide.unreal.discovery import discover_all_engines
            for inst in discover_all_engines():
                inst_root = Path(inst.root) if not isinstance(inst.root, Path) else inst.root
                if inst_root not in candidate_dirs:
                    candidate_dirs.append(inst_root)
        except Exception:
            pass

    program_files = Path(os.environ.get("ProgramFiles", "/Program Files"))
    for ver in ("5.7", "5.6", "5.5", "5.4"):
        candidate_dirs.append(program_files / "Epic Games" / f"UE_{ver}")

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
        notes="Unreal Engine not found in configured host profile or environment variables.",
    )


def discover_unity_engine() -> EngineDiscoveryResult:
    """Discovers installed Unity Editor installations on the local system."""
    custom_unity = os.environ.get("GAMEFORGE_UNITY_PATH") or os.environ.get("UNITY_EDITOR_PATH")
    candidate_dirs: List[Path] = []
    if custom_unity:
        candidate_dirs.append(Path(custom_unity))

    program_files = Path(os.environ.get("ProgramFiles", "/Program Files"))
    hub_editors = program_files / "Unity" / "Hub" / "Editor"
    candidate_dirs.extend([
        hub_editors,
        program_files / "Unity" / "Editor",
    ])

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
    program_files = Path(os.environ.get("ProgramFiles", "/Program Files"))
    vs_msbuild = program_files / "Microsoft Visual Studio" / "2022" / "Community" / "MSBuild" / "Current" / "Bin" / "MSBuild.exe"
    if vs_msbuild.is_file():
        results["msbuild"] = str(vs_msbuild)
    elif shutil.which("msbuild"):
        results["msbuild"] = shutil.which("msbuild")

    # MSVC
    msvc_dir = program_files / "Microsoft Visual Studio" / "2022" / "Community" / "VC" / "Tools" / "MSVC"
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
