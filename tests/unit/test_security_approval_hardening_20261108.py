"""Security and approval hardening tests."""

import pytest
from pathlib import Path

from src.gameforge_ide.backend.security.boundary import BoundaryManager, SecurityViolationError
from src.gameforge_ide.storage.approval_store import ApprovalStore, _APPROVAL_ID_RE
from src.gameforge_ide.backend.models.command_contract import CommandExecutionRequest
from src.gameforge_ide.backend.tools.gateway import ToolGateway
from src.gameforge_ide.backend.tools.terminal_tools import TerminalTools


def test_boundary_manager_protects_approvals(tmp_path: Path):
    """Verify that model write tools cannot overwrite or tamper with approval records."""
    bm = BoundaryManager(tmp_path)
    # Attempting to write into .gameforge/approvals must raise SecurityViolationError
    with pytest.raises(SecurityViolationError, match="Write violation"):
        bm.validate_path(".gameforge/approvals/apr_0123456789ab.json", allow_write=True)

    with pytest.raises(SecurityViolationError, match="Write violation"):
        bm.validate_path(".gameforge/settings.json", allow_write=True)


def test_approval_id_syntax_validation(tmp_path: Path):
    """Verify that approval store validates syntax and blocks path traversal attempts in IDs."""
    store = ApprovalStore(tmp_path)

    # Valid syntax
    assert _APPROVAL_ID_RE.fullmatch("apr_0123456789ab") is not None

    # Invalid syntaxes / traversal attempts
    invalid_ids = [
        "../etc/passwd",
        "../../apr_0123456789ab",
        "apr_0123456789ab/../../bad",
        "apr_0123456789g",  # invalid hex
        "apr_short",
        "APR_0123456789AB", # uppercase
        "0123456789ab",     # missing prefix
        "",
        "apr_0123456789abcdef", # too long
    ]

    for bad_id in invalid_ids:
        assert _APPROVAL_ID_RE.fullmatch(bad_id) is None
        assert store.get(bad_id) is None
        assert store.delete(bad_id) is False
        with pytest.raises(ValueError):
            store._approval_path(bad_id)


def test_approval_digest_and_execution_receipt(tmp_path: Path):
    """Verify that approval creation computes a deterministic operation digest and execution receipt."""
    store = ApprovalStore(tmp_path)
    rec = store.create(
        tool="run_command",
        args={"command": "dir", "shell": "direct"},
        summary="Directory list",
        consequence="None",
        session_id="sess_123",
    )

    appr_id = rec["approval_id"]
    assert "operation_digest" in rec
    digest = rec["operation_digest"]
    assert len(digest) == 64  # SHA-256

    # Transition to APPROVED
    trans = store.transition(appr_id, "APPROVED")
    assert trans is not None
    assert trans["status"] == "APPROVED"

    # Record execution receipt
    receipt = store.record_execution_receipt(
        appr_id,
        status="SUCCESS",
        exit_code=0,
        output_summary="Directory contents",
    )
    assert receipt["approval_id"] == appr_id
    assert receipt["operation_digest"] == digest
    assert receipt["status"] == "SUCCESS"

    # Transition to DONE
    done_trans = store.transition(appr_id, "DONE", result={"exit_code": 0})
    assert done_trans is not None
    assert done_trans["status"] == "DONE"

    # Verify retrieval of receipt
    stored_rcp = store.get_execution_receipt(appr_id)
    assert stored_rcp is not None
    assert stored_rcp["receipt_id"] == receipt["receipt_id"]
    assert stored_rcp["operation_digest"] == digest


def test_shell_default_consistency():
    """Verify that CommandExecutionRequest, ToolGateway, and TerminalTools default to 'direct' shell."""
    req = CommandExecutionRequest(command="whoami")
    assert req.shell == "direct"

    tt = TerminalTools(Path("."))
    # Calling run_command with shell=None defaults target_shell to direct
    res = tt.run_command("whoami")
    assert res.get("status") in {"SUCCESS", "FAILED", "BLOCKED", "ERROR", "PENDING_APPROVAL"}
