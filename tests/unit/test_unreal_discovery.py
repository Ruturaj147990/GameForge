"""Unit tests for the dynamic Unreal Engine discovery subsystem."""
import json
from pathlib import Path
import pytest

from src.gameforge_ide.unreal.discovery import (
    parse_engine_version,
    validate_engine_root,
    scan_manifest_items,
    scan_launcher_installed_dat,
    discover_all_engines,
    get_best_engine,
    DEFAULT_PINNED_VERSION,
)


def _create_mock_engine(
    root: Path,
    major: int = 5,
    minor: int = 7,
    patch: int = 4,
    changelist: int = 51494982,
    has_editor: bool = True,
    has_ubt: bool = True,
    has_remote_exec: bool = True,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    build_dir = root / "Engine" / "Build"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "Build.version").write_text(
        json.dumps({
            "MajorVersion": major,
            "MinorVersion": minor,
            "PatchVersion": patch,
            "Changelist": changelist,
            "BranchName": f"++UE5/Release-{major}.{minor}",
        }),
        encoding="utf-8",
    )

    if has_editor:
        ed_dir = root / "Engine" / "Binaries" / "Win64"
        ed_dir.mkdir(parents=True, exist_ok=True)
        (ed_dir / "UnrealEditor.exe").write_text("mock editor", encoding="utf-8")

    if has_ubt:
        ubt_dir = root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool"
        ubt_dir.mkdir(parents=True, exist_ok=True)
        (ubt_dir / "UnrealBuildTool.dll").write_text("mock ubt", encoding="utf-8")

    if has_remote_exec:
        rx_dir = root / "Engine" / "Plugins" / "Experimental" / "PythonScriptPlugin" / "Content" / "Python"
        rx_dir.mkdir(parents=True, exist_ok=True)
        (rx_dir / "remote_execution.py").write_text("# mock remote execution", encoding="utf-8")

    return root


def test_parse_engine_version_valid(tmp_path: Path):
    eng = _create_mock_engine(tmp_path / "UE_5.7", major=5, minor=7, patch=4, changelist=12345)
    parsed = parse_engine_version(eng)
    assert parsed is not None
    ver, cl, branch = parsed
    assert ver == "5.7.4"
    assert cl == 12345
    assert "5.7" in branch


def test_parse_engine_version_missing(tmp_path: Path):
    assert parse_engine_version(tmp_path / "NonExistent") is None


def test_validate_engine_root_complete(tmp_path: Path):
    eng_dir = _create_mock_engine(tmp_path / "UE_5.7", 5, 7, 4)
    info = validate_engine_root(eng_dir, source="test", pinned_minor="5.7")
    assert info is not None
    assert info.is_valid is True
    assert info.is_compatible is True
    assert info.has_remote_execution is True
    assert info.version == "5.7.4"
    assert info.editor_exe.is_file()
    assert info.ubt_path is not None and info.ubt_path.is_file()
    assert len(info.diagnostics) == 0


def test_validate_engine_root_missing_editor(tmp_path: Path):
    eng_dir = _create_mock_engine(tmp_path / "UE_NoEd", 5, 7, 4, has_editor=False)
    info = validate_engine_root(eng_dir, source="test")
    assert info is not None
    assert info.is_valid is False
    assert any("UnrealEditor.exe not found" in d for d in info.diagnostics)


def test_validate_engine_root_incompatible_version(tmp_path: Path):
    eng_dir = _create_mock_engine(tmp_path / "UE_5.6", 5, 6, 2)
    info = validate_engine_root(eng_dir, source="test", pinned_minor="5.7")
    assert info is not None
    assert info.is_valid is True
    assert info.is_compatible is False
    assert any("differs from target" in d for d in info.diagnostics)


def test_scan_manifest_items(tmp_path: Path, monkeypatch):
    manifest_dir = tmp_path / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))

    target_eng = tmp_path / "Engines" / "UE_5.7"
    _create_mock_engine(target_eng, 5, 7, 4)

    item_data = {
        "AppName": "UE_5.7",
        "DisplayName": "Unreal Engine 5.7",
        "InstallLocation": str(target_eng),
    }
    (manifest_dir / "sample.item").write_text(json.dumps(item_data), encoding="utf-8")

    found = scan_manifest_items()
    assert len(found) == 1
    assert found[0] == target_eng


def test_scan_launcher_installed_dat(tmp_path: Path, monkeypatch):
    dat_dir = tmp_path / "Epic" / "UnrealEngineLauncher"
    dat_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))

    target_eng = tmp_path / "Engines" / "UE_5.7"
    _create_mock_engine(target_eng, 5, 7, 4)

    dat_content = {
        "InstallationList": [
            {"AppName": "UE_5.7", "InstallLocation": str(target_eng)},
        ]
    }
    (dat_dir / "LauncherInstalled.dat").write_text(json.dumps(dat_content), encoding="utf-8")

    found = scan_launcher_installed_dat()
    assert len(found) == 1
    assert found[0] == target_eng


def test_discover_and_get_best_engine(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "empty_progdata"))
    monkeypatch.setenv("GAMEFORGE_SKIP_REGISTRY", "1")

    # Set env override
    eng57 = _create_mock_engine(tmp_path / "UE57", 5, 7, 4, changelist=500000)
    monkeypatch.setenv("GAMEFORGE_ENGINE_ROOT", str(eng57))

    engines = discover_all_engines(pinned_minor="5.7")
    assert len(engines) >= 1
    assert engines[0].root == eng57.resolve()

    best = get_best_engine(pinned_minor="5.7")
    assert best is not None
    assert best.root == eng57.resolve()
