import hashlib
import shutil
from pathlib import Path
import pytest

from src.gameforge_ide.forge.checkpoints import CheckpointError, ProjectRepo

GIT_AVAILABLE = shutil.which("git") is not None


@pytest.mark.skipif(not GIT_AVAILABLE, reason="git binary not available in PATH")
def test_ensure_and_initial_commit(tmp_path: Path):
    proj = tmp_path / "test_proj"
    repo = ProjectRepo(proj)
    assert repo.available is True

    repo.ensure()
    assert (proj / ".git").is_dir()
    assert (proj / ".gitignore").is_file()

    sha = repo.head()
    assert len(sha) == 40

    # Second ensure is a no-op
    repo.ensure()
    assert repo.head() == sha


@pytest.mark.skipif(not GIT_AVAILABLE, reason="git binary not available in PATH")
def test_commit_flow_and_no_change(tmp_path: Path):
    proj = tmp_path / "test_proj"
    repo = ProjectRepo(proj)
    repo.ensure()
    initial_sha = repo.head()

    # Commit without changes returns same sha
    same_sha = repo.commit("no changes")
    assert same_sha == initial_sha

    # Write a new file
    test_file = proj / "Source" / "Game.cpp"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("int main() { return 0; }", encoding="utf-8")

    new_sha = repo.commit("add game.cpp")
    assert new_sha != initial_sha
    assert len(new_sha) == 40
    assert repo.head() == new_sha


@pytest.mark.skipif(not GIT_AVAILABLE, reason="git binary not available in PATH")
def test_reset_to_and_rollback(tmp_path: Path):
    proj = tmp_path / "test_proj"
    repo = ProjectRepo(proj)
    repo.ensure()

    # Create baseline file
    code_file = proj / "Source" / "Actor.cpp"
    code_file.parent.mkdir(parents=True, exist_ok=True)
    code_file.write_text("// Version 1", encoding="utf-8")
    h1 = hashlib.sha256(code_file.read_bytes()).hexdigest()

    sha_v1 = repo.commit("baseline actor")

    # Modify baseline and add untracked extra file
    code_file.write_text("// Version 2 modified", encoding="utf-8")
    extra_file = proj / "Source" / "Extra.cpp"
    extra_file.write_text("// Rogue untracked", encoding="utf-8")

    # Refuse rollback if editor is running
    with pytest.raises(CheckpointError, match="stop the Unreal Editor"):
        repo.reset_to(sha_v1, editor_running=True)

    # Rollback when editor is not running
    repo.reset_to(sha_v1, editor_running=False)

    # Baseline file must be restored byte-for-byte
    assert hashlib.sha256(code_file.read_bytes()).hexdigest() == h1
    assert code_file.read_text(encoding="utf-8") == "// Version 1"
    # Untracked extra file must be cleaned
    assert not extra_file.exists()


@pytest.mark.skipif(not GIT_AVAILABLE, reason="git binary not available in PATH")
def test_changed_since(tmp_path: Path):
    proj = tmp_path / "test_proj"
    repo = ProjectRepo(proj)
    repo.ensure()

    f1 = proj / "f1.txt"
    f1.write_text("one", encoding="utf-8")
    sha1 = repo.commit("f1")

    # Modify f1 and create untracked f2
    f1.write_text("one updated", encoding="utf-8")
    f2 = proj / "f2.txt"
    f2.write_text("two", encoding="utf-8")

    changed = repo.changed_since(sha1)
    assert "f1.txt" in changed
    assert "f2.txt" in changed


@pytest.mark.skipif(not GIT_AVAILABLE, reason="git binary not available in PATH")
def test_max_commit_mb_guard(tmp_path: Path, monkeypatch):
    import src.gameforge_ide.forge.checkpoints as cp

    proj = tmp_path / "test_proj"
    repo = ProjectRepo(proj)
    repo.ensure()

    # Set guard to 0.05 MB (50 KB)
    monkeypatch.setattr(cp, "MAX_COMMIT_MB", 0.05)

    big_file = proj / "BigAsset.bin"
    # Write 100 KB
    big_file.write_bytes(b"\x00" * 100_000)

    with pytest.raises(CheckpointError, match="refusing"):
        repo.commit("try commit large asset")
