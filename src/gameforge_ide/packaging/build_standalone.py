"""Standalone Packaging Builder for GameForge Native PySide6 Desktop Application.

Compliant with GameForge Master Blueprint:
- REQ-055: Standalone desktop packaging launching outside the source tree.
- Never bundles heavy model weights or Ollama blobs.
- Generates reproducible manifest with SHA-256 digests.
- Self-contained launcher entry point.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class StandalonePackager:
    """Packages GameForge IDE as a standalone deployable bundle outside the source tree."""

    VERSION = "1.0.0"
    MAX_PACKAGE_SIZE_MB = 400.0

    FORBIDDEN_PATTERNS = [
        "models/blobs",
        "models/ollama",
        "graders/protected",
        ".git",
        "__pycache__",
        "*.pyc",
        "*.gguf",
        "*.log",
        "*.tmp",
        "pytest_os_temp",
    ]

    def __init__(self, repo_root: Path, dist_root: Optional[Path] = None):
        self.repo_root = repo_root.resolve()
        self.dist_root = (dist_root or (self.repo_root / "dist" / "GameForge")).resolve()

    def _compute_sha256(self, file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    @classmethod
    def _matches_forbidden_pattern(cls, rel_posix: str, item_name: str) -> bool:
        """Match a relative POSIX path or item filename against FORBIDDEN_PATTERNS using fnmatch and path segments."""
        rel_lower = rel_posix.strip("/").lower()
        item_lower = item_name.lower()
        rel_parts = [p for p in rel_lower.split("/") if p]

        for pattern in cls.FORBIDDEN_PATTERNS:
            pat = pattern.replace("\\", "/").strip("/").lower()
            if "/" in pat:
                pat_parts = [p for p in pat.split("/") if p]
                n = len(pat_parts)
                if any(rel_parts[i : i + n] == pat_parts for i in range(len(rel_parts) - n + 1)):
                    return True
                if fnmatch.fnmatch(rel_lower, pat) or fnmatch.fnmatch(rel_lower, f"*/{pat}") or fnmatch.fnmatch(rel_lower, f"{pat}/*"):
                    return True
            else:
                if fnmatch.fnmatch(item_lower, pat) or any(fnmatch.fnmatch(seg, pat) for seg in rel_parts):
                    return True
        return False

    def assemble_bundle(self, clean: bool = True) -> Dict[str, Any]:
        """Assembles standalone distribution directory and writes launcher and manifest."""
        if clean and self.dist_root.exists():
            shutil.rmtree(self.dist_root)

        self.dist_root.mkdir(parents=True, exist_ok=True)
        app_dir = self.dist_root / "app"
        app_dir.mkdir(parents=True, exist_ok=True)

        # 1. Copy core src directory into standalone distribution
        src_target = app_dir / "src"
        if src_target.exists():
            shutil.rmtree(src_target)

        def _ignore_heavy(directory: str, contents: List[str]) -> List[str]:
            ignored = []
            for item in contents:
                full = os.path.join(directory, item)
                rel = os.path.relpath(full, self.repo_root).replace("\\", "/")
                if self._matches_forbidden_pattern(rel, item):
                    ignored.append(item)
            return ignored

        shutil.copytree(
            self.repo_root / "src",
            src_target,
            ignore=_ignore_heavy,
        )

        # 2. Write standalone Windows batch launcher
        bat_launcher = self.dist_root / "GameForge.bat"
        bat_content = (
            "@echo off\r\n"
            "REM GameForge Standalone Desktop Application Launcher\r\n"
            "setlocal\r\n"
            "set SCRIPT_DIR=%~dp0\r\n"
            "set PYTHONPATH=%SCRIPT_DIR%app;%PYTHONPATH%\r\n"
            "python -m src.gameforge_ide.launcher %*\r\n"
            "endlocal\r\n"
        )
        bat_launcher.write_text(bat_content, encoding="utf-8")

        # 3. Write standalone python entry wrapper
        py_launcher = self.dist_root / "gameforge_run.py"
        py_content = (
            "import os, sys\n"
            "from pathlib import Path\n"
            "app_dir = Path(__file__).resolve().parent / 'app'\n"
            "sys.path.insert(0, str(app_dir))\n"
            "from src.gameforge_ide.launcher import main\n"
            "if __name__ == '__main__':\n"
            "    sys.exit(main())\n"
        )
        py_launcher.write_text(py_content, encoding="utf-8")

        # 4. Write portable marker
        (self.dist_root / ".portable").write_text("portable=1\n", encoding="utf-8")

        # 5. Generate manifest with SHA-256 hashes and total size calculation
        total_bytes = 0
        file_hashes: Dict[str, str] = {}
        for root, _, files in os.walk(self.dist_root):
            for f in files:
                p = Path(root) / f
                if p.name == "manifest.json":
                    continue
                sz = p.stat().st_size
                total_bytes += sz
                rel_path = p.relative_to(self.dist_root).as_posix()
                file_hashes[rel_path] = self._compute_sha256(p)

        total_mb = total_bytes / (1024.0 * 1024.0)
        manifest = {
            "app_name": "GameForge Native IDE",
            "version": self.VERSION,
            "target_unreal_engine": "5.7.4",
            "entry_point": "src.gameforge_ide.launcher",
            "max_allowed_footprint_mb": self.MAX_PACKAGE_SIZE_MB,
            "total_size_bytes": total_bytes,
            "total_size_mb": round(total_mb, 2),
            "file_count": len(file_hashes),
            "files": file_hashes,
        }

        manifest_path = self.dist_root / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return {
            "ok": total_mb <= self.MAX_PACKAGE_SIZE_MB,
            "dist_root": str(self.dist_root),
            "manifest_file": str(manifest_path),
            "file_count": len(file_hashes),
            "total_size_mb": round(total_mb, 2),
            "launcher_bat": str(bat_launcher),
            "launcher_py": str(py_launcher),
        }

    def verify_bundle(self) -> Tuple[bool, List[str]]:
        """Validates that packaged bundle is self-contained, <= 400 MB, and free of forbidden artifacts."""
        errors: List[str] = []
        if not self.dist_root.exists():
            return False, ["Distribution directory does not exist"]

        manifest_path = self.dist_root / "manifest.json"
        if not manifest_path.exists():
            errors.append("Manifest missing in distribution directory")

        bat_launcher = self.dist_root / "GameForge.bat"
        if not bat_launcher.exists():
            errors.append("Launcher batch file missing")

        py_launcher = self.dist_root / "gameforge_run.py"
        if not py_launcher.exists():
            errors.append("Launcher python entry wrapper missing")

        # Verify no model weights or protected graders in bundle, and check total size <= 400MB
        total_bytes = 0
        for root, _, files in os.walk(self.dist_root):
            for f in files:
                p = Path(root) / f
                total_bytes += p.stat().st_size
                name_lower = p.name.lower()
                rel_posix = p.relative_to(self.dist_root).as_posix()
                if name_lower.endswith(".gguf") or name_lower.endswith(".bin"):
                    errors.append(f"Model weight binary mistakenly bundled: {p}")
                if self._matches_forbidden_pattern(rel_posix, p.name):
                    errors.append(f"Forbidden artifact mistakenly bundled: {p}")

        total_mb = total_bytes / (1024.0 * 1024.0)
        if total_mb > self.MAX_PACKAGE_SIZE_MB:
            errors.append(
                f"Package footprint {total_mb:.2f} MB exceeds maximum limit of {self.MAX_PACKAGE_SIZE_MB} MB"
            )

        return len(errors) == 0, errors


def main() -> int:
    repo = Path(__file__).resolve().parent.parent.parent.parent
    packager = StandalonePackager(repo)
    print(f"Assembling GameForge standalone bundle from {repo}...")
    res = packager.assemble_bundle()
    ok, errors = packager.verify_bundle()
    if ok:
        print(f"Standalone bundle verified successfully: {res['file_count']} files.")
        print(f"Distribution location: {res['dist_root']}")
        return 0
    else:
        print(f"Bundle verification failed: {errors}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
