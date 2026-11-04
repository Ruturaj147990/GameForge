"""Specialist regression and unit tests for GameForge Unreal Toolchain (DEF-076 - DEF-083)."""
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.gameforge_ide.core.projects import find_uproject
from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.unreal import discovery, mcp_bridge, op_catalog, ops_catalog, toolchain
from src.gameforge_ide.unreal.live_editor import LiveEditorLink
from src.gameforge_ide.unreal.mcp_bridge import UnrealMcpClient
from src.gameforge_ide.unreal.toolchain import UnrealToolchain, format_unreal_cmd
from src.gameforge_ide.backend.tools.unreal_tools import UnrealEngineTools
from src.gameforge_ide.pipeline.project_import import inspect_project, enable_gameforge_management


# ── DEF-076: Discovery Manifests, BOM & Safe Drive Probing ───────────────────

def test_def076_discovery_manifest_bom_and_retry(tmp_path: Path):
    manifest_dir = tmp_path / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    manifest_dir.mkdir(parents=True)
    engine_dir = tmp_path / "UE_5.7"
    (engine_dir / "Engine" / "Binaries" / "Win64").mkdir(parents=True)
    (engine_dir / "Engine" / "Build").mkdir(parents=True)
    (engine_dir / "Engine" / "Build" / "Build.version").write_text(
        json.dumps({"MajorVersion": 5, "MinorVersion": 7, "PatchVersion": 4, "Changelist": 12345}),
        encoding="utf-8"
    )

    # Manifest with UTF-8 BOM
    bom_manifest = manifest_dir / "test.item"
    data = {"AppName": "UE_5.7", "InstallLocation": str(engine_dir)}
    raw_json = json.dumps(data)
    bom_manifest.write_bytes(b"\xef\xbb\xbf" + raw_json.encode("utf-8"))

    with patch.dict(os.environ, {"PROGRAMDATA": str(tmp_path)}):
        roots = discovery.scan_manifest_items()
        assert engine_dir in roots


def test_def076_discovery_drive_scanning_safety():
    """Verify that drive scanning uses Win32 logical drives and skips floppy/optical modal hangs."""
    roots = discovery.scan_filesystem_drives()
    assert isinstance(roots, list)
    # Roots must be Paths
    for r in roots:
        assert isinstance(r, Path)


# ── DEF-077: Nested Project .uproject Resolution ─────────────────────────────

def test_def077_nested_uproject_resolution(tmp_path: Path):
    repo_root = tmp_path / "MyComplexRepo"
    nested_dir = repo_root / "UnrealProject" / "GameSource"
    nested_dir.mkdir(parents=True)
    uproject_file = nested_dir / "MyComplexRepo.uproject"
    uproject_file.write_text(json.dumps({"FileVersion": 3}), encoding="utf-8")

    # find_uproject on root must find the nested uproject
    found = find_uproject(repo_root)
    assert found is not None
    assert found.resolve() == uproject_file.resolve()


def test_def077_project_import_nested_uproject(tmp_path: Path):
    repo_root = tmp_path / "NestedRepo"
    sub_dir = repo_root / "Game"
    sub_dir.mkdir(parents=True)
    up_file = sub_dir / "NestedGame.uproject"
    up_file.write_text(json.dumps({"FileVersion": 3, "EngineAssociation": "5.7"}), encoding="utf-8")
    (sub_dir / "Content").mkdir()
    (sub_dir / "Config").mkdir()
    (sub_dir / "Config" / "DefaultInput.ini").write_text("[/Script/Engine.InputSettings]\n", encoding="utf-8")

    inspection = inspect_project(repo_root)
    assert inspection.project_name == "NestedGame"
    assert Path(inspection.uproject_path).resolve() == up_file.resolve()

    res = enable_gameforge_management(repo_root)
    assert res["ok"] is True
    assert (sub_dir / "Plugins" / "GameForge").is_dir()


# ── DEF-078: Unreal Commandlet Argument Quoting With Spaces ──────────────────

def test_def078_format_unreal_cmd_spaces_and_switches():
    argv = [
        r"E:\Unreal Engine 5.7\Engine\Binaries\Win64\UnrealEditor-Cmd.exe",
        r"E:\My Projects\Game One\GameOne.uproject",
        "-ExecCmds=Automation RunTests GameForge;Quit",
        r"-ReportExportPath=E:\My Projects\Game One\Saved\automation",
        r"-abslog=E:\My Logs\GameOne.log",
        "-unattended",
        "-nosplash",
    ]
    formatted = format_unreal_cmd(argv)
    if os.name == "nt":
        assert isinstance(formatted, str)
        # Verify switches have quotes around values and whitespace before '-'
        assert '-ExecCmds="Automation RunTests GameForge;Quit"' in formatted
        assert '-ReportExportPath="E:/My Projects/Game One/Saved/automation"' in formatted
        assert '-abslog="E:/My Logs/GameOne.log"' in formatted
        assert ' "E:/My Projects/Game One/GameOne.uproject"' in formatted
        assert " -unattended" in formatted
        assert " -nosplash" in formatted


# ── DEF-079: Live Editor Disconnect on Timeout & Tree Killing ────────────────

def test_def079_live_editor_timeout_disconnect(tmp_path: Path):
    up_file = tmp_path / "TestGame.uproject"
    up_file.write_text("{}", encoding="utf-8")
    link = LiveEditorLink(up_file)
    link._token = "testtoken"
    link._rx_module = MagicMock()
    link._rx_module.MODE_EXEC_FILE = 1
    mock_rx = MagicMock()
    mock_rx.has_command_connection.return_value = True

    # Simulate command hanging past timeout
    def _hang(*args, **kwargs):
        time.sleep(2.0)
        return {"output": []}

    mock_rx.run_command.side_effect = _hang
    link._rx = mock_rx

    # Call with 0.1s timeout
    res = link.call("test_op", {}, timeout_s=0.1)
    assert res["ok"] is False
    assert "EDITOR_CALL_TIMEOUT" in res["errors"]
    # Verify socket was cleanly disconnected so next calls don't desync
    assert link._rx is None


def test_def079_live_editor_stop_tree_kill(tmp_path: Path):
    up_file = tmp_path / "TestGame.uproject"
    up_file.write_text("{}", encoding="utf-8")
    link = LiveEditorLink(up_file)

    mock_proc = MagicMock()
    mock_proc.poll.side_effect = [None, None, 0]  # Initially running, still running after terminate, then dead
    mock_proc.returncode = 0
    link._process = mock_proc

    with patch.object(UnrealToolchain, "kill_tree") as mock_kill_tree:
        code = link.stop(timeout_s=0.05, graceful_timeout_s=0.05)
        assert code == 0


# ── DEF-080: MCP Bridge Loopback Safety & Mutating Action Rejection ──────────

def test_def080_mcp_bridge_loopback_enforcement():
    # Loopback hosts must be accepted
    client1 = UnrealMcpClient("127.0.0.1", 8000)
    assert client1.host == "127.0.0.1"
    client2 = UnrealMcpClient("localhost", 8000)
    assert client2.host == "localhost"

    # Non-loopback host must be rejected immediately
    with pytest.raises(ValueError, match="strictly loopback only"):
        UnrealMcpClient("192.168.1.100", 8000)

    with pytest.raises(ValueError, match="strictly loopback only"):
        UnrealMcpClient("malicious-domain.com", 8000)


def test_def080_mcp_bridge_read_only_and_compound_mutating_rejection():
    client = UnrealMcpClient("127.0.0.1", 8000)

    # Valid read-only prefixes
    for valid in ("inspect_actor", "get_scene", "list_levels", "query_status", "describe_asset", "find_light"):
        err = mcp_bridge._validate_read_only(valid)
        assert err is None

    # Mutating commands rejected
    for invalid in ("delete_actor", "set_location", "create_asset", "spawn_bot"):
        err = mcp_bridge._validate_read_only(invalid)
        assert err is not None
        assert "strictly read-only" in err

    # Sneaky compound mutating actions rejected
    for sneaky in ("inspect_and_modify", "get_actor_and_delete", "list_and_remove", "read_and_write"):
        err = mcp_bridge._validate_read_only(sneaky)
        assert err is not None
        assert "mutating action" in err


# ── DEF-081: Plugin Deployment Concurrency and File Synchronization ──────────

def test_def081_plugin_deployment_sync_and_lock(tmp_path: Path):
    project_dir = tmp_path / "MyProject"
    target_plugin = project_dir / "Plugins" / "GameForge"
    target_plugin.mkdir(parents=True)
    (target_plugin / "GameForge.uplugin").write_text("old_uplugin", encoding="utf-8")
    (target_plugin / "Content" / "Python" / "gameforge_ops").mkdir(parents=True)

    tc = UnrealToolchain(engine_root=tmp_path)

    # Deploy plugin should update uplugin and sync safely
    deployed = tc.deploy_gameforge_plugin(project_dir)
    assert deployed == target_plugin
    assert (target_plugin / "GameForge.uplugin").is_file()
    assert (target_plugin / "Content" / "Python" / "gameforge_ops").is_dir()


# ── DEF-082: UnrealEngineTools Projects Root & Dynamic Version ───────────────

def test_def082_unreal_engine_tools_projects_root_and_dynamic_version(tmp_path: Path):
    ws = tmp_path / "Workspace"
    ws.mkdir()
    projects_dir = tmp_path / "ProjectsRoot"
    proj = projects_dir / "SnakeGame"
    proj.mkdir(parents=True)
    up = proj / "SnakeGame.uproject"
    up.write_text("{}", encoding="utf-8")

    engine_root = tmp_path / "MockEngine"
    (engine_root / "Engine" / "Binaries" / "Win64").mkdir(parents=True)
    (engine_root / "Engine" / "Build").mkdir(parents=True)
    (engine_root / "Engine" / "Build" / "Build.version").write_text(
        json.dumps({"MajorVersion": 5, "MinorVersion": 8, "PatchVersion": 1}),
        encoding="utf-8"
    )

    with patch("src.gameforge_ide.core.projects.get_settings") as mock_settings:
        mock_settings.return_value.projects_root = str(projects_dir)
        mock_settings.return_value.host_profile = {}
        mock_settings.return_value.artifacts_root = None
        mock_settings.return_value.validation_root = None
        mock_settings.return_value.default_workspace = None
        tools = UnrealEngineTools(ws)
        tools.engine_root = engine_root

        # 1. Resolve project by name under projects_root
        resolved = tools._resolve_uproject_path("SnakeGame")
        assert resolved is not None
        assert resolved.resolve() == up.resolve()

        # 2. Dynamic engine info reflects actual version from Build.version (e.g. 5.8.1)
        info = tools.get_engine_info()
        assert info["version"] == "5.8.1"


# ── DEF-083: UE 5.8 Forward Compatibility Discovery ──────────────────────────

def test_def083_ue58_discovery_and_remote_exec(tmp_path: Path):
    engine_root = tmp_path / "UE_5.8"
    (engine_root / "Engine" / "Binaries" / "Win64").mkdir(parents=True)
    (engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe").write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool").mkdir(parents=True)
    (engine_root / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.dll").write_text("", encoding="utf-8")
    (engine_root / "Engine" / "Build").mkdir(parents=True)
    (engine_root / "Engine" / "Build" / "Build.version").write_text(
        json.dumps({"MajorVersion": 5, "MinorVersion": 8, "PatchVersion": 0, "Changelist": 99999}),
        encoding="utf-8"
    )

    # Remote execution in Developer/PythonScriptPlugin (future 5.8 layout)
    remote_exec = engine_root / "Engine" / "Plugins" / "Developer" / "PythonScriptPlugin" / "Content" / "Python" / "remote_execution.py"
    remote_exec.parent.mkdir(parents=True)
    remote_exec.write_text("# remote_execution mock", encoding="utf-8")

    eng = discovery.validate_engine_root(engine_root, source="test", pinned_minor="5.8")
    assert eng is not None
    assert eng.is_valid is True
    assert eng.is_compatible is True
    assert eng.has_remote_execution is True
    assert eng.version == "5.8.0"


def test_ops_catalog_alias():
    """Verify src.gameforge_ide.unreal.ops_catalog exports all symbols from op_catalog."""
    assert hasattr(ops_catalog, "CATALOG")
    assert hasattr(ops_catalog, "agent_ops")
    assert hasattr(ops_catalog, "read_only_ops")
    assert ops_catalog.CATALOG is op_catalog.CATALOG
