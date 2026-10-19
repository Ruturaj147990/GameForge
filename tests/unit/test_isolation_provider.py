"""Unit tests for Execution Isolation Provider and Capability Auditing (Deliverable F)."""

import os
import sys
from pathlib import Path
import pytest

from gameforge_bench.isolation import (
    IsolationAuditResult,
    IsolationLevel,
    RestrictedProcessIsolationProvider,
    audit_os_isolation_capabilities,
)


def test_os_isolation_capability_audit():
    """Audits local OS and verifies truthful classification reporting."""
    audit = audit_os_isolation_capabilities()
    assert isinstance(audit, IsolationAuditResult)
    assert audit.host_os != ""
    assert IsolationLevel.TRUSTED_LOCAL.value in audit.supported_classifications
    assert IsolationLevel.LOW_PRIVILEGE_PROCESS.value in audit.supported_classifications
    # Never claim OS_SANDBOX_VERIFIED without an active hypervisor or container sandbox
    if not (audit.hyper_v_active and (audit.containers_available or audit.windows_sandbox_available)):
        assert IsolationLevel.OS_SANDBOX_VERIFIED.value not in audit.supported_classifications
    assert audit.default_classification == IsolationLevel.LOW_PRIVILEGE_PROCESS.value


def test_restricted_process_provider_execution(tmp_path):
    """Executes a benign command under restricted process isolation and checks outputs and duration."""
    provider = RestrictedProcessIsolationProvider()
    assert provider.classification == IsolationLevel.LOW_PRIVILEGE_PROCESS

    code = "import sys; print('SANDBOX_HELLO'); sys.exit(0)"
    cmd = [sys.executable, "-c", code]
    ret, stdout, stderr, dur = provider.execute(cmd, cwd=tmp_path, timeout_seconds=10.0)

    assert ret == 0
    assert "SANDBOX_HELLO" in stdout
    assert dur > 0.0


def test_restricted_process_provider_timeout_enforcement(tmp_path):
    """Verifies that processes exceeding declared timeout are terminated safely."""
    provider = RestrictedProcessIsolationProvider()
    code = "import time; time.sleep(5.0)"
    cmd = [sys.executable, "-c", code]

    ret, stdout, stderr, dur = provider.execute(cmd, cwd=tmp_path, timeout_seconds=0.5)
    assert ret == -1
    assert "exceeding timeout" in stderr or dur >= 0.5


def test_environment_sanitization(tmp_path, monkeypatch):
    """Sensitive environment variables (tokens, secrets) must be stripped from candidate process."""
    monkeypatch.setenv("SECRET_API_TOKEN", "super_secret_123")
    monkeypatch.setenv("SAFE_CONFIG_PATH", "configs/test")

    provider = RestrictedProcessIsolationProvider()
    code = "import os; print('TOKEN_FOUND' if 'SECRET_API_TOKEN' in os.environ else 'TOKEN_STRIPPED'); print('SAFE_FOUND' if 'SAFE_CONFIG_PATH' in os.environ else 'SAFE_MISSING')"
    cmd = [sys.executable, "-c", code]

    ret, stdout, stderr, dur = provider.execute(cmd, cwd=tmp_path, timeout_seconds=5.0)
    assert ret == 0
    assert "TOKEN_STRIPPED" in stdout
    assert "SAFE_FOUND" in stdout


def test_sentinel_boundary_check(tmp_path):
    """Tests sentinel access verification on harmless test paths."""
    provider = RestrictedProcessIsolationProvider()

    safe_path = tmp_path / "candidate_scratch" / "data.bin"
    assert provider.verify_sentinel_access(safe_path) is True

    forbidden_grader = Path("graders/protected/t2_004/test_health_damage_hidden.py")
    assert provider.verify_sentinel_access(forbidden_grader) is False

    forbidden_criteria = Path("configs/acceptance_criteria/t2_004_health_damage.json")
    assert provider.verify_sentinel_access(forbidden_criteria) is False


def test_workspace_preparation_and_cleanup(tmp_path):
    """Verifies that isolated workspace is created, populated, and safely torn down between runs."""
    provider = RestrictedProcessIsolationProvider()
    src = tmp_path / "src_candidate"
    src.mkdir()
    (src / "game.txt").write_text("sample content", encoding="utf-8")

    ws = tmp_path / "run_ws"
    assert provider.prepare_workspace(src, ws) is True
    assert (ws / "game.txt").is_file()

    provider.cleanup(ws)
    assert not ws.exists(), "Workspace must be completely discarded/reset after run"
