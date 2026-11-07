"""Comprehensive unit tests for Unreal Target Separation, UAT Packaging Hardening (DEF-308),
Plugin Drift Detection & Synchronization (DEF-309), Asset Integrity, and Truthful Engine Reporting.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.gameforge_ide.core.projects import find_packaged_executable
from src.gameforge_ide.forge.validation import validate_stage_output
from src.gameforge_ide.unreal import discovery, mcp_bridge, ue58_lane
from src.gameforge_ide.unreal.asset_integrity import (
    UE_PACKAGE_TAG,
    check_uasset_integrity,
    validate_content_directory,
)
from src.gameforge_ide.unreal.plugin_manifest import (
    compute_plugin_manifest,
    detect_plugin_drift,
    get_authoritative_plugin_root,
    synchronize_plugin,
)
from src.gameforge_ide.unreal.toolchain import (
    PackagingPhase,
    StepResult,
    UnrealToolchain,
    verify_packaged_output,
)


# ── 1. Target Separation (Editor target vs Game target) ────────────────────────

def test_target_separation_editor_vs_game(tmp_path: Path):
    """Verify that Editor and Standalone Game targets are strictly separated in UBT invocations."""
    project_dir = tmp_path / "MyGame"
    project_dir.mkdir(parents=True)
    uproject = project_dir / "MyGame.uproject"
    uproject.write_text("{}", encoding="utf-8")

    engine_root = tmp_path / "EngineRoot"
    (engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool").mkdir(parents=True)
    ubt = engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe"
    ubt.write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Binaries" / "DotNET" / "AutomationTool").mkdir(parents=True)
    uat = engine_root / "Engine" / "Binaries" / "DotNET" / "AutomationTool" / "AutomationTool.exe"
    uat.write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Binaries" / "Win64").mkdir(parents=True)
    (engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe").write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Build").mkdir(parents=True)
    (engine_root / "Engine" / "Build" / "Build.version").write_text(
        json.dumps({"MajorVersion": 5, "MinorVersion": 7, "PatchVersion": 4, "Changelist": 51494982}),
        encoding="utf-8"
    )

    tc = UnrealToolchain(engine_root=engine_root)

    with patch.object(tc, "_run") as mock_run:
        mock_run.return_value = StepResult(True, "build", 0, 1.0, str(tmp_path / "build.log"))

        # Phase 1: Editor target compilation
        res_ed = tc.build_editor_target(uproject, configuration="Development", platform="Win64")
        assert res_ed.ok is True
        assert res_ed.data["phase"] == PackagingPhase.PHASE_1_EDITOR_COMPILE.value

        call_argv = mock_run.call_args[0][1]
        assert call_argv[1] == "MyGameEditor"
        assert call_argv[2] == "Win64"
        assert call_argv[3] == "Development"

        # Phase 2: Standalone game target compilation
        # Create the expected game target binary so build_game_target verifies it
        bin_dir = project_dir / "Binaries" / "Win64"
        bin_dir.mkdir(parents=True)
        game_exe = bin_dir / "MyGame.exe"
        game_exe.write_bytes(b"\x90\x00\x00\x00")

        res_game = tc.build_game_target(uproject, configuration="Development", platform="Win64")
        assert res_game.ok is True
        assert res_game.data["phase"] == PackagingPhase.PHASE_2_GAME_COMPILE.value
        assert res_game.data["game_target_exe"] == str(game_exe)

        call_argv_game = mock_run.call_args[0][1]
        assert call_argv_game[1] == "MyGame"
        assert call_argv_game[2] == "Win64"
        assert call_argv_game[3] == "Development"


def test_build_game_target_verifies_monolithic_binary_on_disk(tmp_path: Path):
    """If UBT reports success but the standalone binary was not generated, build_game_target fails."""
    project_dir = tmp_path / "TestGame"
    project_dir.mkdir(parents=True)
    uproject = project_dir / "TestGame.uproject"
    uproject.write_text("{}", encoding="utf-8")

    engine_root = tmp_path / "EngineRoot"
    (engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool").mkdir(parents=True)
    ubt = engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe"
    ubt.write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Binaries" / "DotNET" / "AutomationTool").mkdir(parents=True)
    (engine_root / "Engine" / "Binaries" / "DotNET" / "AutomationTool" / "AutomationTool.exe").write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Binaries" / "Win64").mkdir(parents=True)
    (engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe").write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Build").mkdir(parents=True)
    (engine_root / "Engine" / "Build" / "Build.version").write_text(
        json.dumps({"MajorVersion": 5, "MinorVersion": 7, "PatchVersion": 4, "Changelist": 51494982}),
        encoding="utf-8"
    )

    tc = UnrealToolchain(engine_root=engine_root)

    with patch.object(tc, "_run") as mock_run:
        # Mock UBT returning 0 exit code, but NO binary written into Binaries/Win64
        mock_run.return_value = StepResult(True, "build", 0, 1.0, str(tmp_path / "build.log"))
        res = tc.build_game_target(uproject, configuration="Development", platform="Win64")
        assert res.ok is False
        assert any("monolithic executable not found" in e for e in res.errors)


# ── 2. Prevention of Exit Code 25 (DEF-308) ────────────────────────────────────

def test_package_prevents_exit_code_25_missing_game_binary(tmp_path: Path):
    """DEF-308: If standalone game binary is missing and its build fails, package() fails safely with ExitCode 25."""
    project_dir = tmp_path / "ActionGame"
    project_dir.mkdir(parents=True)
    uproject = project_dir / "ActionGame.uproject"
    uproject.write_text("{}", encoding="utf-8")

    archive_dir = project_dir / "Packaged"

    engine_root = tmp_path / "EngineRoot"
    (engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool").mkdir(parents=True)
    (engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe").write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Binaries" / "DotNET" / "AutomationTool").mkdir(parents=True)
    (engine_root / "Engine" / "Binaries" / "DotNET" / "AutomationTool" / "AutomationTool.exe").write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Binaries" / "Win64").mkdir(parents=True)
    (engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe").write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Build").mkdir(parents=True)
    (engine_root / "Engine" / "Build" / "Build.version").write_text(
        json.dumps({"MajorVersion": 5, "MinorVersion": 7, "PatchVersion": 4, "Changelist": 51494982}),
        encoding="utf-8"
    )

    tc = UnrealToolchain(engine_root=engine_root)

    with patch.object(tc, "build_game_target") as mock_build_game:
        # Standalone game build fails
        mock_build_game.return_value = StepResult(
            False, "build", exit_code=6, duration_s=2.5, errors=["Compilation error C2065 in ActionGame.cpp"]
        )

        with patch.object(tc, "_run") as mock_run:
            res = tc.package(uproject, archive_dir=archive_dir, configuration="Development", platform="Win64")
            # Must return exit_code 25 to mark missing executable interception
            assert res.ok is False
            assert res.exit_code == 25
            assert any("DEF-308" in e for e in res.errors)
            assert any("ExitCode=25" in e for e in res.errors)
            # UAT must NOT have been called with -skipbuildeditor
            mock_run.assert_not_called()


def test_package_succeeds_when_game_target_and_staging_complete(tmp_path: Path):
    """When standalone game executable exists and UAT finishes staging, package() verifies Phase 6."""
    project_dir = tmp_path / "ValidGame"
    project_dir.mkdir(parents=True)
    uproject = project_dir / "ValidGame.uproject"
    uproject.write_text("{}", encoding="utf-8")

    archive_dir = project_dir / "Packaged"

    # Pre-existing game binary in Binaries/Win64
    bin_dir = project_dir / "Binaries" / "Win64"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ValidGame.exe").write_bytes(b"\x90\x00\x00\x00")

    engine_root = tmp_path / "EngineRoot"
    (engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool").mkdir(parents=True)
    (engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe").write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Binaries" / "DotNET" / "AutomationTool").mkdir(parents=True)
    (engine_root / "Engine" / "Binaries" / "DotNET" / "AutomationTool" / "AutomationTool.exe").write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Binaries" / "Win64").mkdir(parents=True)
    (engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe").write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Build").mkdir(parents=True)
    (engine_root / "Engine" / "Build" / "Build.version").write_text(
        json.dumps({"MajorVersion": 5, "MinorVersion": 7, "PatchVersion": 4, "Changelist": 51494982}),
        encoding="utf-8"
    )

    tc = UnrealToolchain(engine_root=engine_root)

    # Set up valid packaged staging structure in archive_dir
    win_pkg = archive_dir / "Windows"
    (win_pkg / "ValidGame" / "Binaries" / "Win64").mkdir(parents=True)
    (win_pkg / "ValidGame" / "Binaries" / "Win64" / "ValidGame.exe").write_bytes(b"\x90\x00\x00\x00")
    (win_pkg / "ValidGame" / "Content").mkdir(parents=True)
    (win_pkg / "ValidGame" / "Content" / "Level.pak").write_bytes(b"\x00" * 100)
    (win_pkg / "ValidGame.exe").write_bytes(b"\x90\x00\x00\x00")

    log_path = tmp_path / "package.log"
    log_path.write_text("BuildCookRun completed successfully", encoding="utf-8")

    with patch.object(tc, "_run") as mock_run:
        mock_run.return_value = StepResult(True, "package", exit_code=0, duration_s=12.0, log_path=str(log_path))
        res = tc.package(uproject, archive_dir=archive_dir, configuration="Development", platform="Win64")

        assert res.ok is True
        assert res.data["verified_structure"] is True
        assert res.data["exe_exists"] is True
        assert "Phase 1: Editor target compilation" in res.data["phases"]
        assert "Phase 2: Standalone game target compilation" in res.data["phases"]
        assert "Phase 6: Verification of packaged output" in res.data["phases"]


# ── 3. Rejection of Binaries/Win64 as False Proof of Packaging ─────────────────

def test_validation_rejects_raw_binaries_in_binaries_win64(tmp_path: Path):
    """CRITICAL: validation.py strictly rejects an executable located in Binaries/Win64 as proof of packaging."""
    project_dir = tmp_path / "MyProject"
    project_dir.mkdir(parents=True)
    raw_exe = project_dir / "Binaries" / "Win64" / "MyProject.exe"
    raw_exe.parent.mkdir(parents=True)
    raw_exe.write_bytes(b"\x90\x00\x00\x00")

    # Pass raw binary as outcome exe
    valid, issues = validate_stage_output("package", {"exe": str(raw_exe)}, project_dir=project_dir)
    assert valid is False
    assert any("REJECTED: Raw executable" in iss for iss in issues)
    assert any("Binaries/Win64" in iss for iss in issues)


def test_validation_rejects_fallback_to_binaries_win64(tmp_path: Path):
    """If package output is empty and only Binaries/Win64 exists, validation fails."""
    project_dir = tmp_path / "MyProject2"
    project_dir.mkdir(parents=True)
    raw_exe = project_dir / "Binaries" / "Win64" / "MyProject2.exe"
    raw_exe.parent.mkdir(parents=True)
    raw_exe.write_bytes(b"\x90\x00\x00\x00")

    # No explicit exe passed; fallback scan must NOT accept Binaries/Win64
    valid, issues = validate_stage_output("package", {}, project_dir=project_dir)
    assert valid is False
    assert any("Package stage produced no packaged executable on disk in Packaged/" in iss for iss in issues)


def test_find_packaged_executable_rejects_binaries_win64(tmp_path: Path):
    """find_packaged_executable() returns None when only Binaries/Win64 exists."""
    project_dir = tmp_path / "GameA"
    project_dir.mkdir(parents=True)
    raw_exe = project_dir / "Binaries" / "Win64" / "GameA.exe"
    raw_exe.parent.mkdir(parents=True)
    raw_exe.write_bytes(b"\x90\x00\x00\x00")

    # Must be None
    found = find_packaged_executable(project_dir, "GameA")
    assert found is None

    # Once staged in Packaged/Windows/, it returns the packaged executable
    pkg_exe = project_dir / "Packaged" / "Windows" / "GameA.exe"
    pkg_exe.parent.mkdir(parents=True)
    pkg_exe.write_bytes(b"\x90\x00\x00\x00")

    found_staged = find_packaged_executable(project_dir, "GameA")
    assert found_staged == pkg_exe


def test_verify_packaged_output_checks_staging_integrity(tmp_path: Path):
    """verify_packaged_output() enforces complete staged structure."""
    archive_dir = tmp_path / "PkgTest"
    archive_dir.mkdir(parents=True)

    # 1. Missing Windows dir
    ok, issues, _ = verify_packaged_output(archive_dir, "GameX")
    assert ok is False
    assert any("does not exist" in i for i in issues)

    # 2. Windows dir with only root exe, missing staged dir
    win_dir = archive_dir / "Windows"
    win_dir.mkdir(parents=True)
    (win_dir / "GameX.exe").write_bytes(b"\x90\x00")

    ok, issues, _ = verify_packaged_output(archive_dir, "GameX")
    assert ok is False
    assert any("Staged project directory" in i for i in issues)

    # 3. Complete valid structure
    staged_bin = win_dir / "GameX" / "Binaries" / "Win64"
    staged_bin.mkdir(parents=True)
    (staged_bin / "GameX.exe").write_bytes(b"\x90\x00")
    staged_content = win_dir / "GameX" / "Content"
    staged_content.mkdir(parents=True)
    (staged_content / "Content.pak").write_bytes(b"\x00" * 50)

    ok, issues, _ = verify_packaged_output(archive_dir, "GameX")
    assert ok is True
    assert len(issues) == 0


# ── 4. Plugin Drift Detection & Authoritative Synchronization (DEF-309) ───────

def test_authoritative_manifest_generation():
    """Verify authoritative manifest is computed with versioning and interface hashes."""
    auth_root = get_authoritative_plugin_root()
    assert auth_root.is_dir()

    manifest = compute_plugin_manifest(auth_root)
    assert manifest["manifest_version"] == 1
    assert manifest["plugin_name"] == "GameForge"
    assert manifest["plugin_version"] == "1.0.0"
    assert manifest["engine_version"] == "5.7.0"
    assert manifest["total_files"] >= 80

    # Key interfaces must be tracked with valid SHA-256
    assert "GameForge.uplugin" in manifest["interfaces"]
    assert "Source/GameForgeRuntime/Public/GameForgePlayer.h" in manifest["interfaces"]
    assert "Source/GameForgeRuntime/Public/GameForgeScenario.h" in manifest["interfaces"]
    assert "Source/GameForgeRuntime/Public/GameForgeRules.h" in manifest["interfaces"]
    for iface, h in manifest["interfaces"].items():
        assert len(h) == 64  # SHA-256 length


def test_drift_detection_and_synchronization(tmp_path: Path):
    """Test drift detection on missing, modified, and stale files, and clean synchronization."""
    target_plugin = tmp_path / "TargetPlugins" / "GameForge"
    auth_root = get_authoritative_plugin_root()

    # 1. Non-existent target has drift
    drift_initial = detect_plugin_drift(auth_root, target_plugin)
    assert drift_initial.has_drift is True
    assert drift_initial.target_exists is False

    # 2. Perform synchronization
    sync_res = synchronize_plugin(auth_root, target_plugin, remove_stale=True)
    assert sync_res["ok"] is True
    assert sync_res["copied_count"] >= 80

    # Post-sync: 0 drift
    drift_after_sync = detect_plugin_drift(auth_root, target_plugin)
    assert drift_after_sync.has_drift is False
    assert drift_after_sync.version_mismatch is False
    assert len(drift_after_sync.missing_files) == 0
    assert len(drift_after_sync.mismatched_files) == 0
    assert len(drift_after_sync.stale_files) == 0

    # 3. Simulate drift: tamper with a file, delete a file, add an orphaned stale file
    tampered_file = target_plugin / "Source" / "GameForgeRuntime" / "Public" / "GameForgePlayer.h"
    tampered_file.write_text("// Modified interface", encoding="utf-8")

    deleted_file = target_plugin / "Config" / "FilterPlugin.ini"
    deleted_file.unlink()

    stale_file = target_plugin / "Source" / "OldObsoleteClass.cpp"
    stale_file.write_text("// Orphaned stale source causing C2084 collision", encoding="utf-8")

    drift_tampered = detect_plugin_drift(auth_root, target_plugin)
    assert drift_tampered.has_drift is True
    assert "Source/GameForgeRuntime/Public/GameForgePlayer.h" in drift_tampered.mismatched_files
    assert "Config/FilterPlugin.ini" in drift_tampered.missing_files
    assert "Source/OldObsoleteClass.cpp" in drift_tampered.stale_files
    assert "Source/GameForgeRuntime/Public/GameForgePlayer.h" in drift_tampered.interface_drift

    # 4. Clean re-synchronization fixes drift and deletes the stale file
    resync = synchronize_plugin(auth_root, target_plugin, remove_stale=True)
    assert "Source/OldObsoleteClass.cpp" in resync["removed_stale_files"]
    assert not stale_file.exists()

    drift_clean = detect_plugin_drift(auth_root, target_plugin)
    assert drift_clean.has_drift is False


# ── 5. Asset Integrity and Mock Contamination Prevention ──────────────────────

def test_check_uasset_integrity():
    """Verify binary header and size checking on Unreal assets."""
    # Valid binary uasset mock
    valid_content = UE_PACKAGE_TAG + b"\x00" * 60
    assert len(valid_content) >= 32

    # Plaintext mock asset
    mock_content = b"mock dummy placeholder asset text data"

    assert check_uasset_integrity(Path("non_existent_file.uasset"))[0] is False

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".uasset", delete=False) as f_valid:
        f_valid.write(valid_content)
        valid_path = Path(f_valid.name)

    with tempfile.NamedTemporaryFile(suffix=".uasset", delete=False) as f_empty:
        empty_path = Path(f_empty.name)

    with tempfile.NamedTemporaryFile(suffix=".uasset", delete=False) as f_mock:
        f_mock.write(mock_content)
        mock_path = Path(f_mock.name)

    try:
        ok, _ = check_uasset_integrity(valid_path)
        assert ok is True

        ok_empty, err_empty = check_uasset_integrity(empty_path)
        assert ok_empty is False
        assert "0 bytes" in err_empty

        ok_mock, err_mock = check_uasset_integrity(mock_path)
        assert ok_mock is False
        assert "mock" in err_mock.lower() or "ascii" in err_mock.lower()
    finally:
        valid_path.unlink(missing_ok=True)
        empty_path.unlink(missing_ok=True)
        mock_path.unlink(missing_ok=True)


def test_validate_content_directory_detects_contamination(tmp_path: Path):
    """validate_content_directory() detects corrupt files and mock asset contamination."""
    content_dir = tmp_path / "Content"
    content_dir.mkdir(parents=True)

    # Valid asset
    valid_asset = content_dir / "SM_Crate.uasset"
    valid_asset.write_bytes(UE_PACKAGE_TAG + b"\x00" * 40)

    # Mock contaminated asset
    mock_asset = content_dir / "mock_test_box.uasset"
    mock_asset.write_bytes(UE_PACKAGE_TAG + b"\x00" * 40)

    # 0-byte corrupt asset
    corrupt_asset = content_dir / "BrokenMesh.uasset"
    corrupt_asset.write_bytes(b"")

    ok, issues, stats = validate_content_directory(content_dir, allow_mock_assets=False)
    assert ok is False
    assert stats["mock_count"] >= 1
    assert stats["corrupt_count"] >= 1
    assert any("Mock asset contamination" in i for i in issues)
    assert any("Corrupt 0-byte asset" in i for i in issues)


# ── 6. Truthful Engine Version Reporting (UE 5.7 vs UE 5.8) ───────────────────

def test_engine_discovery_finds_ue57_pinned():
    """Verify that discovery detects UE 5.7.4 on the local host."""
    best = discovery.get_best_engine(pinned_minor="5.7")
    assert best is not None
    assert best.major_minor == "5.7"
    assert best.is_valid is True
    assert best.is_compatible is True
    assert best.root == Path(r"E:\UE\UE_5.7")


def test_ue58_lane_reports_truthfully_blocked_by_environment():
    """UE 5.8 is not installed on disk; report must be truthfully BLOCKED BY ENVIRONMENT."""
    report = ue58_lane.get_ue58_lane_report()
    assert report["status"] == "BLOCKED BY ENVIRONMENT"
    assert report["channel"] == "next"
    assert report["is_installed"] is False
    assert report["is_active"] is False
    assert report["engine_root"] is None
    assert "BLOCKED BY ENVIRONMENT" in ue58_lane.get_ue58_status_string()
    assert ue58_lane.is_ue58_installed() is False
    assert ue58_lane.is_ue58_active() is False

    # Pinned engine info must be present and verified
    assert report["pinned_engine"]["version"] == "5.7.4"
    assert report["pinned_engine"]["verified"] is True

    # MCP bridge port coexistence must pass
    assert report["mcp_bridge"]["port_coexistence"]["coexistence_valid"] is True
    assert report["mcp_bridge"]["editor_port"] == 47815
    assert report["mcp_bridge"]["mcp_port"] == 8000
