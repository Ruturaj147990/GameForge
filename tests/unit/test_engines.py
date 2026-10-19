"""Unit tests for engine adapters, discovery, and safe subprocess execution."""

from pathlib import Path
from gameforge_bench.engines.base import EngineDiscoveryResult, safe_subprocess_run
from gameforge_bench.engines.discovery import (
    discover_environment,
    discover_toolchains,
    discover_unity_engine,
    discover_unreal_engine,
)
from gameforge_bench.engines.unity import UnityEngineAdapter
from gameforge_bench.engines.unreal import UnrealEngineAdapter


def test_discover_unreal_engine():
    res = discover_unreal_engine()
    assert isinstance(res, EngineDiscoveryResult)
    assert res.engine_name == "unreal"
    if res.is_installed:
        assert res.version is not None
        assert res.executable_path is not None
        assert Path(res.executable_path).is_file()


def test_discover_unity_engine():
    res = discover_unity_engine()
    assert isinstance(res, EngineDiscoveryResult)
    assert res.engine_name == "unity"
    # Even if not installed, returns clean structure with notes
    assert isinstance(res.is_installed, bool)


def test_discover_toolchains():
    tc = discover_toolchains()
    assert "python" in tc
    assert tc["python"] is not None


def test_subprocess_timeout_behavior(tmp_path):
    # Run a command that takes longer than the timeout
    # On Windows PowerShell, Start-Sleep
    res = safe_subprocess_run(
        ["powershell", "-Command", "Start-Sleep -Seconds 5"],
        timeout_seconds=0.5,
        log_dir=tmp_path,
    )
    assert res.timed_out is True
    assert res.return_code == -999
    assert res.stderr_log_path is not None
    assert Path(res.stderr_log_path).is_file()


def test_subprocess_return_code_and_logs(tmp_path):
    res = safe_subprocess_run(
        ["powershell", "-Command", "Write-Output 'TEST_OUTPUT_123'"],
        timeout_seconds=10,
        log_dir=tmp_path,
    )
    assert res.timed_out is False
    assert res.return_code == 0
    assert "TEST_OUTPUT_123" in res.stdout
    assert res.stdout_log_path is not None


def test_unity_batchmode_cli_construction():
    mock_disc = EngineDiscoveryResult(
        engine_name="unity",
        is_installed=True,
        executable_path=r"C:\Program Files\Unity\Editor\Unity.exe",
    )
    adapter = UnityEngineAdapter(mock_disc)
    proj_path = Path(r"C:\fake\unity_project")
    log_path = Path(r"C:\fake\logs\build.log")

    cmd = adapter.build_batchmode_args(
        project_path=proj_path,
        log_file=log_path,
        execute_method="GameForge.Editor.Build",
        extra_args=["-customFlag"],
    )

    assert cmd[0] == r"C:\Program Files\Unity\Editor\Unity.exe"
    assert "-batchmode" in cmd
    assert "-nographics" in cmd
    assert "-quit" in cmd
    assert "-projectPath" in cmd
    assert str(proj_path) in cmd
    assert "-logFile" in cmd
    assert str(log_path) in cmd
    assert "-executeMethod" in cmd
    assert "GameForge.Editor.Build" in cmd
    assert "-customFlag" in cmd


def test_unity_uninstalled_behavior(tmp_path):
    mock_disc = EngineDiscoveryResult(engine_name="unity", is_installed=False)
    adapter = UnityEngineAdapter(mock_disc)

    build_res = adapter.build_project(tmp_path, tmp_path)
    assert build_res.success is False
    assert build_res.is_infrastructure_failure is True
    assert "UNVERIFIED" in build_res.log_output

    test_res = adapter.execute_automated_tests(tmp_path, tmp_path)
    assert len(test_res) == 1
    assert test_res[0].passed is False

    probes_res = adapter.execute_behavior_probes(tmp_path, tmp_path, {})
    assert len(probes_res) == 1
    assert probes_res[0].passed is False


def test_unreal_project_structure_validation(tmp_path):
    adapter = UnrealEngineAdapter()
    is_valid, msg = adapter.validate_project_structure(tmp_path)
    assert is_valid is False
    assert "No .uproject" in msg

    # Create dummy uproject
    uproj = tmp_path / "Test.uproject"
    uproj.write_text('{"FileVersion": 3}', encoding="utf-8")
    is_valid, msg = adapter.validate_project_structure(tmp_path)
    assert is_valid is True
