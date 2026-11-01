"""Test that GameForge runtime operates cleanly without repo root or configs/ (WI-11.2)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from src.gameforge_ide.core.settings import PACKAGE_ROOT


def test_runtime_paths_without_repo(tmp_path: Path):
    """Simulate a packaged installation by copying src/gameforge_ide to a temp dir without configs/."""
    isolated_root = tmp_path / "app"
    isolated_root.mkdir(parents=True, exist_ok=True)
    target_pkg = isolated_root / "gameforge_ide"

    # Copy src/gameforge_ide ignoring __pycache__
    shutil.copytree(
        PACKAGE_ROOT,
        target_pkg,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    # Verify configs/ is NOT present in isolated root
    assert not (isolated_root / "configs").exists()

    # Code to run in isolated subprocess
    test_code = """
import sys
from pathlib import Path
from gameforge_ide.core.settings import get_settings, get_ops_root, get_plugin_root, PACKAGE_ROOT

# Verify PACKAGE_ROOT points to the isolated gameforge_ide
assert PACKAGE_ROOT.name == "gameforge_ide", f"Unexpected PACKAGE_ROOT: {PACKAGE_ROOT}"

# Verify ops and plugin roots exist under PACKAGE_ROOT
ops_root = get_ops_root()
assert ops_root.is_dir(), f"ops_root does not exist: {ops_root}"

plugin_root = get_plugin_root()
assert plugin_root.is_dir(), f"plugin_root does not exist: {plugin_root}"
assert (plugin_root / "GameForge.uplugin").is_file(), "GameForge.uplugin missing"

# Verify settings initialize without dev host profiles
s = get_settings()
assert s.bridge_port == 47815
assert s.ollama_url.startswith("http")

# Verify op catalog loads
from gameforge_ide.unreal.op_catalog import CATALOG
assert len(CATALOG) >= 120, f"Catalog smaller than expected: {len(CATALOG)}"

print("ISOLATED_OK")
"""

    env = dict(os.environ)
    # Remove dev host profile and repo references
    env.pop("GAMEFORGE_HOST_PROFILE", None)
    env.pop("GAMEFORGE_WORKSPACE", None)
    env["PYTHONPATH"] = str(isolated_root)

    cmd = [sys.executable, "-c", test_code]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(isolated_root))
    assert proc.returncode == 0, f"Isolated run failed: STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "ISOLATED_OK" in proc.stdout
