"""Unit tests for static policy checks and candidate isolation boundaries."""

from pathlib import Path
from gameforge_bench.policy import check_candidate_policy, snapshot_directory_hashes


def test_clean_candidate_passes_policy(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    candidate = workspace / "candidate"
    candidate.mkdir()

    # Create allowed file
    source_file = candidate / "Source" / "Player.cpp"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("// valid player code", encoding="utf-8")

    res = check_candidate_policy(
        workspace_root=workspace,
        candidate_dir=candidate,
        allowed_edit_paths=["project gameplay source paths"],
        forbidden_paths=["tests", "grader"],
    )

    assert res.passed is True
    assert len(res.violations) == 0


def test_tampering_with_protected_paths_detected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    candidate = workspace / "candidate"
    candidate.mkdir()

    # Candidate attempts to modify a protected grader/test file
    bad_file = candidate / "graders" / "fake_grader.py"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text("print('always pass')", encoding="utf-8")

    res = check_candidate_policy(
        workspace_root=workspace,
        candidate_dir=candidate,
        allowed_edit_paths=["Source"],
        forbidden_paths=["graders", "tests"],
    )

    assert res.passed is False
    assert any("Tampering detected" in v or "Protected security violation" in v for v in res.violations)


def test_forbidden_file_detected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    candidate = workspace / "candidate"
    candidate.mkdir()

    # Candidate modifies tests
    bad_test = candidate / "tests" / "test_something.py"
    bad_test.parent.mkdir(parents=True)
    bad_test.write_text("# delete test assertions", encoding="utf-8")

    res = check_candidate_policy(
        workspace_root=workspace,
        candidate_dir=candidate,
        allowed_edit_paths=["Source"],
        forbidden_paths=["tests"],
    )

    assert res.passed is False
    assert any("tests" in v.lower() for v in res.violations)
