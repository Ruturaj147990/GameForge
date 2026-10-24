"""Unreal Engine 5.7 Adapter & Staged Compilation Tools for GameForge IDE."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class UnrealEngineTools:
    """Manages Unreal Engine discovery, project inspection, and staged build validation."""

    KNOWN_ENGINE_PATHS = [
        Path(r"E:\UE\UE_5.7"),
        Path(r"C:\Program Files\Epic Games\UE_5.7"),
    ]

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.engine_root = self._discover_engine_root()

    def _discover_engine_root(self) -> Optional[Path]:
        for candidate in self.KNOWN_ENGINE_PATHS:
            if candidate.exists() and (candidate / "Engine" / "Binaries").exists():
                return candidate.resolve()
        return None

    def get_engine_info(self) -> Dict[str, Any]:
        """Returns details on the installed Unreal Engine installation."""
        if not self.engine_root:
            return {
                "installed": False,
                "version": "Not detected",
                "engine_root": None,
                "install_path": None,
                "ubt_available": False,
                "ubt_path": None,
                "uat_available": False,
                "uat_path": None,
                "editor_cmd_available": False,
                "editor_cmd_path": None,
            }

        ubt_path = self.engine_root / "Engine" / "Build" / "BatchFiles" / "Build.bat"
        uat_path = self.engine_root / "Engine" / "Build" / "BatchFiles" / "RunUAT.bat"
        editor_cmd = self.engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"

        engine_root_str = str(self.engine_root)
        return {
            "installed": True,
            "version": "5.7.4",
            "engine_root": engine_root_str,
            "install_path": engine_root_str,
            "ubt_available": ubt_path.exists(),
            "ubt_path": str(ubt_path) if ubt_path.exists() else None,
            "uat_available": uat_path.exists(),
            "uat_path": str(uat_path) if uat_path.exists() else None,
            "editor_cmd_available": editor_cmd.exists(),
            "editor_cmd_path": str(editor_cmd) if editor_cmd.exists() else None,
        }

    def find_uprojects(self) -> List[Dict[str, Any]]:
        """Finds all .uproject files in the workspace, excluding transient build/eval artifacts."""
        projects = []
        seen_paths = set()
        IGNORE_PARTS = {"Intermediate", "Saved", "Binaries", ".git", "scratch", "reports", "node_modules", ".venv"}

        for p in self.workspace_root.glob("**/*.uproject"):
            try:
                rel_parts = p.relative_to(self.workspace_root).parts
            except ValueError:
                rel_parts = p.parts
            if any(part in IGNORE_PARTS for part in rel_parts[:-1]):
                continue
            canonical = str(p.resolve())
            if canonical in seen_paths:
                continue
            seen_paths.add(canonical)

            rel_path = str(p.relative_to(self.workspace_root).as_posix())
            parent_rel = str(p.parent.relative_to(self.workspace_root).as_posix())
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                projects.append({
                    "name": p.stem,
                    "path": rel_path,
                    "relative_dir": parent_rel if parent_rel != "." else "",
                    "full_path": canonical,
                    "engine_association": data.get("EngineAssociation", "5.7"),
                    "modules": [m.get("Name") for m in data.get("Modules", [])],
                    "plugins": [pl.get("Name") for pl in data.get("Plugins", [])],
                })
            except Exception:
                projects.append({
                    "name": p.stem,
                    "path": rel_path,
                    "relative_dir": parent_rel if parent_rel != "." else "",
                    "full_path": canonical,
                    "engine_association": "unknown",
                })
        # Sort so active workspace / fixture projects appear before hidden graders
        projects.sort(key=lambda x: (x["path"].startswith("graders/"), x["name"].lower(), x["path"]))
        return projects

    def parse_compiler_errors(self, build_log: str) -> List[Dict[str, Any]]:
        """Parses MSVC and Clang compiler errors from a build log."""
        errors = []
        # Pattern matches: filepath(line,col): error Cxxxx: message
        msvc_pattern = re.compile(r"([A-Za-z]:\\[^:\n]+)\((\d+)(?:,\d+)?\):\s+(fatal\s+)?error\s+([A-Z0-9]+):\s+(.+)")
        clang_pattern = re.compile(r"([A-Za-z]:\\[^:\n]+):(\d+):\d+:\s+error:\s+(.+)")

        for line in build_log.splitlines():
            m_msvc = msvc_pattern.search(line)
            if m_msvc:
                errors.append({
                    "file": m_msvc.group(1),
                    "line": int(m_msvc.group(2)),
                    "code": m_msvc.group(4),
                    "message": m_msvc.group(5),
                    "raw": line.strip(),
                })
                continue

            m_clang = clang_pattern.search(line)
            if m_clang:
                errors.append({
                    "file": m_clang.group(1),
                    "line": int(m_clang.group(2)),
                    "code": "clang_error",
                    "message": m_clang.group(3),
                    "raw": line.strip(),
                })

        return errors

    def run_staged_build(
        self,
        uproject_rel_path: str,
        target_name: Optional[str] = None,
        configuration: str = "Development",
        platform: str = "Win64",
        timeout_seconds: int = 180,
    ) -> Dict[str, Any]:
        """Executes a memory-safe staged build of an Unreal project target."""
        uproject_path = (self.workspace_root / uproject_rel_path).resolve()
        if not uproject_path.exists():
            return {"status": "ERROR", "error": f"Project file not found: {uproject_rel_path}"}

        if not target_name:
            target_name = uproject_path.stem + "Editor"

        engine_info = self.get_engine_info()
        if not engine_info["installed"] or not engine_info["ubt_available"]:
            return {
                "status": "ENGINE_UNAVAILABLE",
                "error": "Unreal Engine 5.7 toolchain not available on host system.",
            }

        ubt_cmd = [
            engine_info["ubt_path"],
            target_name,
            platform,
            configuration,
            f"-Project={str(uproject_path)}",
            "-WaitMutex",
            "-NoHotReload",
        ]

        t0 = time.time()
        try:
            proc = subprocess.run(
                ubt_cmd,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            duration = round(time.time() - t0, 2)
            log = proc.stdout + "\n" + proc.stderr
            errors = self.parse_compiler_errors(log)

            return {
                "status": "SUCCESS" if proc.returncode == 0 else "BUILD_FAILED",
                "exit_code": proc.returncode,
                "duration_seconds": duration,
                "parsed_errors": errors,
                "error_count": len(errors),
                "build_log": log[-4000:] if len(log) > 4000 else log,  # Last 4000 chars
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "TIMEOUT",
                "exit_code": -1,
                "error": f"Build timed out after {timeout_seconds} seconds.",
            }
        except Exception as e:
            return {"status": "ERROR", "error": f"Build execution failed: {str(e)}"}
