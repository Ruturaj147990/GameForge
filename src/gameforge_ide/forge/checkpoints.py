"""Per-project git checkpoints. GameForge owns the repo inside each generated project; commits are local only."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import List, Optional

UE_GITIGNORE = """# GameForge-managed project repo (checkpoints)
Binaries/
Intermediate/
Saved/
DerivedDataCache/
Packaged/
Plugins/*
!Plugins/GameForge/
Plugins/GameForge/Binaries/
Plugins/GameForge/Intermediate/
.vs/
*.sln
*.VC.db
*.opendb
"""
MAX_COMMIT_MB = 200.0


class CheckpointError(RuntimeError):
    pass


class ProjectRepo:
    def __init__(self, project_dir: Path | str, git: Optional[str] = None):
        self.dir = Path(project_dir).resolve()
        self.git = git or shutil.which("git")

    @property
    def available(self) -> bool:
        return self.git is not None

    def _clear_stale_index_lock(self) -> None:
        lock_file = self.dir / ".git" / "index.lock"
        if lock_file.is_file():
            try:
                lock_file.unlink(missing_ok=True)
            except Exception:
                pass

    def _clear_readonly_flags(self) -> None:
        """On Windows, clear read-only attributes on working tree files to prevent git permission errors."""
        try:
            for root, dirs, files in os.walk(self.dir):
                if ".git" in dirs:
                    dirs.remove(".git")
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        os.chmod(fp, stat.S_IWRITE | stat.S_IREAD)
                    except Exception:
                        pass
        except Exception:
            pass

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        if not self.git:
            raise CheckpointError("git is not installed; checkpoints are disabled")
        self._clear_stale_index_lock()
        res = subprocess.run(
            [self.git, "-C", str(self.dir), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if check and res.returncode != 0:
            raise CheckpointError(f"git {' '.join(args)} failed: {res.stderr.strip()[:500]}")
        return res

    def ensure(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        is_new = not (self.dir / ".git").is_dir()
        if is_new:
            self._run("init", "-q")
        self._clear_stale_index_lock()
        # Guarantee author identity and consistent line endings even if repo pre-existed
        try:
            self._run("config", "user.name", "GameForge", check=False)
            self._run("config", "user.email", "gameforge@localhost", check=False)
            self._run("config", "core.autocrlf", "false", check=False)
        except Exception:
            pass
        gi = self.dir / ".gitignore"
        if not gi.exists():
            gi.write_text(UE_GITIGNORE, encoding="utf-8", newline="\n")
        if is_new:
            self._run("add", "-A")
            self._run("commit", "-q", "--allow-empty", "-m", "forge: initial")

    def head(self) -> str:
        return self._run("rev-parse", "HEAD").stdout.strip()

    def commit(self, message: str) -> str:
        """Commit everything not ignored; returns HEAD (unchanged if nothing changed)."""
        self._clear_stale_index_lock()
        self._run("add", "-A")
        if not self._run("status", "--porcelain").stdout.strip():
            return self.head()
        staged = self._run("diff", "--cached", "--numstat").stdout  # binary files show "-\t-"
        size_mb = 0.0
        for line in staged.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                raw_path = parts[-1].strip()
                if " => " in raw_path:
                    if "{" in raw_path and "}" in raw_path:
                        pre = raw_path[:raw_path.find("{")]
                        post = raw_path[raw_path.find("}") + 1:]
                        rename_part = raw_path[raw_path.find("{") + 1:raw_path.find("}")]
                        new_sub = rename_part.split(" => ")[-1]
                        raw_path = f"{pre}{new_sub}{post}"
                    else:
                        raw_path = raw_path.split(" => ")[-1]
                fpath = self.dir / raw_path
                if fpath.is_file():
                    size_mb += fpath.stat().st_size / 1e6
        if size_mb > MAX_COMMIT_MB:
            self._run("reset", "-q")
            raise CheckpointError(f"checkpoint would add {size_mb:.0f} MB (> {MAX_COMMIT_MB} MB); refusing")
        self._run("commit", "-q", "-m", message)
        return self.head()

    def reset_to(self, sha: str, editor_running: bool) -> None:
        """Hard reset + clean of non-ignored files. Refuses while an editor holds the project's files."""
        if editor_running:
            raise CheckpointError("stop the Unreal Editor for this project before rolling back")
        self._run("cat-file", "-e", f"{sha}^{{commit}}")
        self._clear_stale_index_lock()
        self._clear_readonly_flags()
        self._run("reset", "-q", "--hard", sha)
        self._clear_readonly_flags()
        self._run("clean", "-q", "-fd")

    def changed_since(self, sha: str) -> List[str]:
        out = self._run("diff", "--name-only", sha, "--").stdout.splitlines()
        untracked = self._run("ls-files", "--others", "--exclude-standard").stdout.splitlines()
        return sorted(set(out) | set(untracked))
