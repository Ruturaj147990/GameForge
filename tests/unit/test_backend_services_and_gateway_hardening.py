"""Comprehensive regression and unit tests for backend services, boundary security, and tool gateway hardening (DEF-082 through DEF-086)."""

from __future__ import annotations

import os
import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.backend.security.boundary import (
    BoundaryManager,
    SecurityViolationError,
)
from src.gameforge_ide.backend.tools.gateway import (
    ToolGateway,
    TOOL_ALIASES,
)
from src.gameforge_ide.backend.providers.hosted import (
    HostedModel,
    HostedProfile,
    SpendCapExceeded,
    SpendLedger,
    GuardedProvider,
    EgressPolicy,
    CredentialStore,
    _post_json,
    redact,
)
from src.gameforge_ide.desktop.services.projects_service import (
    GameSummary,
    find_project_thumbnail,
    load_runs_index,
    list_games,
    delete_project,
    ProjectsService,
)
from src.gameforge_ide.core.systems import (
    SystemRow,
    SystemsSnapshot,
    probe_ollama,
    probe_ram,
    probe_disk,
)
from src.gameforge_ide.desktop.services.systems_service import SystemsService
from src.gameforge_ide.core.settings import Settings, get_settings


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


# =============================================================================
# DEF-082: BoundaryManager Hardening Tests
# =============================================================================

def test_boundary_rejects_workspace_root_as_write_target(tmp_path):
    bm = BoundaryManager(tmp_path)
    # Valid read for workspace root
    assert bm.validate_path(".", allow_write=False) == tmp_path.resolve()

    # Reject write to workspace root directly
    with pytest.raises(SecurityViolationError, match="Cannot modify or overwrite the workspace root"):
        bm.validate_path(".", allow_write=True)

    with pytest.raises(SecurityViolationError, match="Empty path cannot be written to"):
        bm.validate_path("", allow_write=True)


def test_boundary_rejects_alternate_data_streams(tmp_path):
    bm = BoundaryManager(tmp_path)
    with pytest.raises(SecurityViolationError, match="Alternate data stream violation"):
        bm.validate_path("source/file.cpp:hidden.exe")

    with pytest.raises(SecurityViolationError, match="Alternate data stream violation"):
        bm.validate_path("test:payload")


def test_boundary_rejects_reserved_device_names(tmp_path):
    bm = BoundaryManager(tmp_path)
    for dev in ["CON", "con.txt", "PRN", "aux.dat", "NUL", "COM1", "lpt2.bin"]:
        with pytest.raises(SecurityViolationError, match="Reserved device violation"):
            bm.validate_path(dev)
        with pytest.raises(SecurityViolationError, match="Reserved device violation"):
            bm.validate_path(f"subdir/{dev}")


def test_boundary_distinguishes_git_folder_vs_gitignore(tmp_path):
    bm = BoundaryManager(tmp_path)
    # Writing to .git or internal files must be blocked
    with pytest.raises(SecurityViolationError, match="protected system path"):
        bm.validate_path(".git/config", allow_write=True)
    with pytest.raises(SecurityViolationError, match="protected system path"):
        bm.validate_path("submodule/.git/HEAD", allow_write=True)

    # Writing to .gitignore or .gitattributes MUST be allowed
    git_ignore = bm.validate_path(".gitignore", allow_write=True)
    assert git_ignore == (tmp_path / ".gitignore").resolve()

    git_attr = bm.validate_path("Source/.gitattributes", allow_write=True)
    assert git_attr == (tmp_path / "Source" / ".gitattributes").resolve()

    # Writing to a legitimate file with git in its name
    git_md = bm.validate_path("docs/git_workflow.md", allow_write=True)
    assert git_md == (tmp_path / "docs" / "git_workflow.md").resolve()


# =============================================================================
# DEF-083: ToolGateway Hardening & Alias Dispatch Tests
# =============================================================================

def test_gateway_alias_mapping_and_approval_gate(tmp_path):
    gw = ToolGateway(tmp_path)

    # Aliases must map to approval-gated canonical definitions
    assert "apply_diff" in TOOL_ALIASES
    assert TOOL_ALIASES["apply_diff"] == "apply_edit"

    # tool_requires_approval must return True for mutating aliases
    assert gw.tool_requires_approval("apply_diff", {}) is True
    assert gw.tool_requires_approval("apply_diffs_batch", {}) is True
    assert gw.tool_requires_approval("rollback_diff", {}) is True
    assert gw.tool_requires_approval("rollback_diffs_batch", {}) is True

    # Unknown tools must fail-closed (require approval / cannot bypass)
    assert gw.tool_requires_approval("unregistered_malicious_tool", {}) is True

    # execute_tool without approval must block
    res = gw.execute_tool("apply_diff", {"diff_id": "diff-123"}, approval_granted=False)
    assert res["status"] == "PENDING_APPROVAL"
    assert "requires explicit user approval" in res["error"]


def test_gateway_validates_required_parameters(tmp_path):
    gw = ToolGateway(tmp_path)

    # read_file requires 'subpath'
    res = gw.execute_tool("read_file", {}, approval_granted=False)
    assert res["status"] == "ERROR"
    assert "Missing required parameter" in res["error"]
    assert "subpath" in res["error"]

    # propose_edit requires 'subpath' and 'replacement_content'
    res_edit = gw.execute_tool("propose_edit", {"subpath": "test.txt"}, approval_granted=False)
    assert res_edit["status"] == "ERROR"
    assert "Missing required parameter" in res_edit["error"]
    assert "replacement_content" in res_edit["error"]


def test_gateway_search_index_boundary_validation(tmp_path):
    gw = ToolGateway(tmp_path)

    # Disallow index search outside workspace
    outside_dir = tmp_path.parent / "non_workspace_outside"
    outside_dir.mkdir(parents=True, exist_ok=True)

    res = gw.execute_tool("search_index", {"query": "Test", "project": str(outside_dir)})
    assert res["status"] == "BLOCKED"
    assert "outside workspace" in res["error"].lower()


# =============================================================================
# DEF-084: SpendLedger & Hosted Provider Hardening Tests
# =============================================================================

def test_spend_ledger_concurrent_writes(tmp_path):
    ledger = SpendLedger(tmp_path)
    prof = HostedProfile(
        provider_id="concurrent_prov",
        kind="openai_compatible",
        base_url="http://mock",
        models=[HostedModel(id="m1", display_name="M1", max_context=1000, usd_per_mtok_in=1.0, usd_per_mtok_out=2.0)],
        per_day_usd_cap=100.0,
    )
    model = prof.models[0]

    errors = []

    def worker(i: int):
        try:
            # Different SpendLedger instances accessing same file
            inst = SpendLedger(tmp_path)
            for j in range(10):
                inst.record(prof, model, f"task_{i}", 1000, 1000)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent writes threw errors: {errors}"
    assert ledger.spent("concurrent_prov") > 0.0


def test_spend_ledger_corrupted_lines_resilience(tmp_path):
    spend_file = tmp_path / ".gameforge" / "spend.jsonl"
    spend_file.parent.mkdir(parents=True, exist_ok=True)
    # Write valid and corrupted lines
    spend_file.write_text(
        '{"ts": 100, "day": "2026-11-04", "provider_id": "test_p", "usd": 0.50}\n'
        'CORRUPTED_JSON_LINE\n'
        '{"missing_fields": true}\n'
        '{"ts": 101, "day": "2026-11-04", "provider_id": "test_p", "usd": "invalid_num"}\n'
        '{"ts": 102, "day": "2026-11-04", "provider_id": "test_p", "usd": 0.25}\n',
        encoding="utf-8",
    )

    ledger = SpendLedger(tmp_path)
    total = ledger.spent("test_p", day="2026-11-04")
    assert total == pytest.approx(0.75)


def test_spend_ledger_in_flight_reservation_prevents_cap_overrun(tmp_path):
    ledger = SpendLedger(tmp_path)
    prof = HostedProfile(
        provider_id="cap_prov",
        kind="openai_compatible",
        base_url="http://mock",
        models=[HostedModel(id="m1", display_name="M1", max_context=1000, usd_per_mtok_in=10.0, usd_per_mtok_out=10.0)],
        per_day_usd_cap=1.0,
        per_task_usd_cap=1.0,
    )

    # Initial check passes
    ledger.check(prof, "task_1", 0.60)
    ledger.reserve(prof, "task_1", 0.60)

    # Second check for another request of 0.60 must fail because 0.60 + 0.60 > 1.0
    with pytest.raises(SpendCapExceeded):
        ledger.check(prof, "task_1", 0.60)

    # Releasing reservation allows subsequent check
    ledger.release_reservation(prof, "task_1", 0.60)
    ledger.check(prof, "task_1", 0.60)


def test_guarded_provider_complete_redacts_credentials_on_error(tmp_path):
    prof = HostedProfile(
        provider_id="err_prov",
        kind="openai_compatible",
        base_url="http://invalid.nowhere:9999",
        models=[HostedModel(id="m1", display_name="M1", max_context=1000, usd_per_mtok_in=1.0, usd_per_mtok_out=1.0)],
        enabled=True,
    )
    EgressPolicy(tmp_path).allow("err_prov")

    class _SecretCreds(CredentialStore):
        def get(self, p):
            return "sk-super-secret-123456789"

    from src.gameforge_ide.backend.providers.hosted import OpenAICompatibleHostedProvider
    inner = OpenAICompatibleHostedProvider(prof, _SecretCreds())
    guarded = GuardedProvider(inner, tmp_path)

    with pytest.raises(RuntimeError) as exc_info:
        guarded.complete("m1", "ping")

    err_text = str(exc_info.value)
    assert "sk-super-secret-123456789" not in err_text
    assert "***REDACTED***" in err_text or "HOSTED_ERROR" in err_text


# =============================================================================
# DEF-085: ProjectsService Hardening Tests
# =============================================================================

def test_list_games_handles_null_and_corrupt_timestamps(tmp_path):
    proj_dir = tmp_path / "MyProject"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "MyProject.uproject").write_text("{}", encoding="utf-8")

    runs_file = tmp_path / ".gameforge" / "runs_index.json"
    runs_file.parent.mkdir(parents=True, exist_ok=True)
    runs_file.write_text(
        json.dumps([
            {"run_id": "r1", "project_dir": str(proj_dir), "updated_at": None},
            {"run_id": "r2", "project_dir": str(proj_dir), "updated_at": "invalid_date"},
            {"run_id": "r3", "project_dir": str(proj_dir), "updated_at": 1700000000.0},
            "corrupted_non_dict_entry",
        ]),
        encoding="utf-8",
    )

    games = list_games(projects_root=tmp_path, workspace_dir=tmp_path)
    assert len(games) == 1
    assert games[0].name == "MyProject"
    assert games[0].last_run_time == 1700000000.0


def test_delete_project_refuses_critical_root_directories(tmp_path):
    # Attempting to delete current working directory must raise PermissionError
    with pytest.raises(PermissionError, match="Safety violation"):
        delete_project("root_attempt", project_dir=Path.cwd())

    # Attempting to delete filesystem root
    drive_root = Path.cwd().anchor
    with pytest.raises(PermissionError, match="Safety violation"):
        delete_project("drive_root", project_dir=Path(drive_root))


def test_delete_project_cleans_runs_index_with_null_project_dir(tmp_path):
    proj = tmp_path / "DeleteMe"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "DeleteMe.uproject").write_text("{}", encoding="utf-8")

    idx_file = tmp_path / ".gameforge" / "runs_index.json"
    idx_file.parent.mkdir(parents=True, exist_ok=True)
    idx_file.write_text(
        json.dumps([
            {"run_id": "r1", "project_dir": None, "project_name": "DeleteMe"},
            {"run_id": "r2", "project_dir": str(proj), "project_name": "DeleteMe"},
            {"run_id": "r3", "project_dir": str(tmp_path / "KeepMe"), "project_name": "KeepMe"},
        ]),
        encoding="utf-8",
    )

    success = delete_project("DeleteMe", projects_root=tmp_path, project_dir=proj)
    assert success is True
    assert not proj.exists()

    remaining_runs = json.loads(idx_file.read_text(encoding="utf-8"))
    assert len(remaining_runs) == 1
    assert remaining_runs[0]["project_name"] == "KeepMe"


def test_find_project_thumbnail_ignores_empty_png(tmp_path):
    evidence_dir = tmp_path / "Saved" / "GameForge" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    empty_png = evidence_dir / "empty.png"
    empty_png.write_bytes(b"")

    assert find_project_thumbnail(tmp_path) is None

    valid_png = evidence_dir / "valid.png"
    valid_png.write_bytes(b"\x89PNG\r\n\x1a\nfakeimagebytes")
    thumb = find_project_thumbnail(tmp_path)
    assert thumb is not None
    assert thumb.name == "valid.png"


# =============================================================================
# DEF-086: Systems Probing & Deduplication Tests
# =============================================================================

def test_probe_ollama_safe_with_null_size_vram():
    settings = get_settings()

    # Mock response with size_vram=None and 0 models
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp_tags = MagicMock()
        mock_resp_tags.read.return_value = json.dumps({"models": []}).encode("utf-8")
        mock_resp_tags.__enter__.return_value = mock_resp_tags

        mock_resp_ps = MagicMock()
        mock_resp_ps.read.return_value = json.dumps({"models": [{"size_vram": None}]}).encode("utf-8")
        mock_resp_ps.__enter__.return_value = mock_resp_ps

        mock_url.side_effect = [mock_resp_tags, mock_resp_ps]

        row = probe_ollama(settings)
        assert row.key == "ollama"
        assert row.state == "degraded"
        assert "0 models installed" in row.summary


def test_systems_snapshot_overall_local_first_resilience():
    r1 = SystemRow(key="ollama", state="ok", summary="4 models")
    r2 = SystemRow(key="engine", state="ok", summary="UE 5.7.4")
    r3 = SystemRow(key="editor", state="ok", summary="1 active")
    r4 = SystemRow(key="ram", state="ok", summary="30% used")
    r5 = SystemRow(key="disk", state="ok", summary="100 GB free")
    # Hosted is opt-in, degraded by default when user is offline/local-only
    r6 = SystemRow(key="hosted", state="degraded", summary="No hosted profiles opted in")

    snapshot = SystemsSnapshot(rows=(r1, r2, r3, r4, r5, r6), taken_at=time.time())
    assert snapshot.overall == "ok"


def test_systems_service_probe_deduplication(qapp, tmp_path):
    service = SystemsService(workspace_root=tmp_path, auto_start=False)
    assert service._is_probing is False

    # First refresh initiates probe
    service.refresh_now()
    assert service._is_probing is True

    # Immediate second refresh does not duplicate job
    service.refresh_now()
    assert service._is_probing is True
    service.stop()
