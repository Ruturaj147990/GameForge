"""Storage hygiene: cap, retention, rotation, protected files."""

import json
import os
import time

from src.gameforge_ide.backend import storage_hygiene as sh


def _mk(path, size, age_days=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    t = time.time() - age_days * 86400
    os.utime(path, (t, t))


def test_plan_prunes_oldest_until_under_cap_and_keeps_protected(tmp_path):
    g = tmp_path / ".gameforge"
    for i in range(10):
        _mk(g / "diffs" / f"d{i}.json", 1_000_000, age_days=10 - i)
    _mk(g / "sessions" / "s.json", 3_000_000)               # never pruned
    _mk(g / "spend.jsonl", 500_000)                         # audit record, protected
    (g / "approvals").mkdir(parents=True)
    (g / "approvals" / "apr_pending.json").write_text(json.dumps({"status": "PENDING"}))
    (g / "approvals" / "apr_done.json").write_text(json.dumps({"status": "DONE"}))
    os.utime(g / "approvals" / "apr_done.json", (time.time() - 40 * 86400,) * 2)
    pl = sh.plan(tmp_path, cap_bytes=8_000_000)
    names = [os.path.basename(p) for p in pl.delete]
    assert "apr_done.json" in names and "apr_pending.json" not in names
    assert "s.json" not in names and "spend.jsonl" not in names
    assert names.index("d0.json") < names.index("d1.json")   # oldest first
    sh.apply(tmp_path, pl)
    assert sh.plan(tmp_path, cap_bytes=8_000_000).total_bytes <= 8_000_000
    assert (g / "approvals" / "apr_pending.json").exists() and (g / "spend.jsonl").exists()


def test_old_items_pruned_even_under_cap(tmp_path):
    _mk(tmp_path / ".gameforge" / "tasks" / "old.json", 10, age_days=45)
    _mk(tmp_path / ".gameforge" / "tasks" / "new.json", 10, age_days=1)
    names = [os.path.basename(p) for p in sh.plan(tmp_path).delete]
    assert names == ["old.json"]


def test_log_rotation_keeps_bounded_history(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "LOG_ROTATE_BYTES", 100)
    log = tmp_path / ".gameforge" / "agent.log"
    for i in range(sh.LOG_KEEP + 2):
        _mk(log, 200)
        sh.apply(tmp_path, sh.plan(tmp_path))
    rotated = sorted(p.name for p in log.parent.glob("agent.log.*"))
    assert len(rotated) == sh.LOG_KEEP and not log.exists()
