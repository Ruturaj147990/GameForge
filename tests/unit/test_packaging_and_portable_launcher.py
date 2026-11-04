"""Unit tests for standalone desktop packaging, <= 400 MB footprint verification, and portable launcher (REQ-055)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.gameforge_ide.launcher import _is_portable_mode, _resolve_workspace
from src.gameforge_ide.packaging.build_standalone import StandalonePackager


def test_standalone_packager_footprint_within_budget(tmp_path: Path):
    repo = tmp_path / "mock_repo"
    src_dir = repo / "src" / "gameforge_ide"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("# GameForge\n", encoding="utf-8")
    (src_dir / "launcher.py").write_text("# Launcher\n", encoding="utf-8")

    dist = tmp_path / "dist" / "GameForge"
    packager = StandalonePackager(repo_root=repo, dist_root=dist)
    res = packager.assemble_bundle(clean=True)

    assert res["ok"] is True
    assert res["total_size_mb"] < 400.0
    assert packager.MAX_PACKAGE_SIZE_MB == 400.0

    ok, errors = packager.verify_bundle()
    assert ok is True
    assert not errors

    # Check manifest content
    manifest_path = Path(res["manifest_file"])
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["max_allowed_footprint_mb"] == 400.0
    assert "total_size_mb" in manifest
    assert manifest["total_size_mb"] < 400.0
    assert (dist / ".portable").is_file()


def test_standalone_packager_rejects_oversized_footprint(tmp_path: Path):
    repo = tmp_path / "mock_repo"
    src_dir = repo / "src" / "gameforge_ide"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("# GameForge\n", encoding="utf-8")

    dist = tmp_path / "dist" / "GameForge"
    packager = StandalonePackager(repo_root=repo, dist_root=dist)
    packager.assemble_bundle(clean=True)

    # Intentionally write a 405 MB dummy file inside dist to simulate footprint breach
    oversized_file = dist / "app" / "large_payload.dat"
    with open(oversized_file, "wb") as f:
        # Seek and write last byte to create sparse 405MB file instantly
        f.seek(405 * 1024 * 1024)
        f.write(b"\0")

    ok, errors = packager.verify_bundle()
    assert ok is False
    assert any("exceeds maximum limit of 400.0 MB" in e for e in errors)


def test_portable_workspace_resolution(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GAMEFORGE_PORTABLE", "1")
    assert _is_portable_mode() is True

    ws = _resolve_workspace(portable=True)
    assert ws.exists()
    assert ws.is_dir()
