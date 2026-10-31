import os
import time
from pathlib import Path
import pytest

from src.gameforge_ide.forge.model import RunSpec, RunState, StepKind, StepRecord, StepSpec, StepStatus
from src.gameforge_ide.forge.store import RunStore


def _make_state(run_id: str, ws: Path, project_dir: Path | None = None, title: str = "Test") -> RunState:
    s = StepSpec(step_id="step1", kind=StepKind.DESIGN, title="Design")
    run = RunSpec(
        run_id=run_id,
        title=title,
        workspace_dir=str(ws),
        project_dir=str(project_dir) if project_dir else None,
        steps=[s],
    )
    return RunState.new(run)


def test_run_dir_resolution(tmp_path: Path):
    ws = tmp_path / "workspace"
    proj = tmp_path / "projects" / "MyProject"

    # Workspace-only store
    store_ws = RunStore(project_dir=None, workspace_dir=ws)
    assert store_ws.run_dir("run_1") == ws / ".gameforge" / "runs" / "run_1"

    # Project store
    store_proj = RunStore(project_dir=proj, workspace_dir=ws)
    assert store_proj.run_dir("run_1") == proj / "Saved" / "GameForge" / "runs" / "run_1"


def test_save_and_load_state(tmp_path: Path):
    ws = tmp_path / "ws"
    proj = tmp_path / "proj"
    store = RunStore(project_dir=proj, workspace_dir=ws)

    state = _make_state("run_101", ws, proj, "SaveLoad Test")
    state.records["step1"].status = StepStatus.DONE
    state.records["step1"].data = {"out": 42}
    saved_path = store.save(state)
    assert saved_path.is_file()

    loaded = store.load("run_101")
    assert loaded is not None
    assert loaded.run.run_id == "run_101"
    assert loaded.records["step1"].status == StepStatus.DONE
    assert loaded.records["step1"].data == {"out": 42}

    # Nonexistent run returns None
    assert store.load("run_missing") is None


def test_events_logging(tmp_path: Path):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    store.append_event("run_ev", {"kind": "start", "val": 1})
    store.append_event("run_ev", {"kind": "progress", "val": 2})
    store.append_event("run_ev", {"kind": "done", "val": 3})

    events = store.load_events("run_ev")
    assert len(events) == 3
    assert events[0]["kind"] == "start"
    assert events[1]["val"] == 2
    assert "t" in events[2]


def test_latest_for_project(tmp_path: Path):
    ws = tmp_path / "ws"
    proj = tmp_path / "proj"
    store = RunStore(project_dir=proj, workspace_dir=ws)

    # Initially None
    assert store.latest_for_project(proj) is None

    # Run 1
    s1 = _make_state("run_001", ws, proj, "Run 1")
    s1.updated_at = 100.0
    store.save(s1)

    # Run 2 (later)
    s2 = _make_state("run_002", ws, proj, "Run 2")
    s2.updated_at = 200.0
    store.save(s2)

    latest = store.latest_for_project(proj)
    assert latest is not None
    assert latest.run.run_id == "run_002"


def test_runs_index_cap_and_order(tmp_path: Path):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)

    # Create 210 runs
    for i in range(210):
        st = _make_state(f"run_{i:03d}", ws, title=f"Run {i}")
        st.updated_at = float(i)
        store.save(st)

    idx = store.get_runs_index()
    assert len(idx) == 200
    # Newest (highest updated_at) should be at the front
    assert idx[0]["run_id"] == "run_209"
    assert idx[-1]["run_id"] == "run_010"


def test_save_retry_on_permission_error(tmp_path: Path, monkeypatch):
    ws = tmp_path / "ws"
    store = RunStore(project_dir=None, workspace_dir=ws)
    st = _make_state("run_retry", ws)

    orig_replace = os.replace
    call_count = 0

    def flaky_replace(src, dst):
        nonlocal call_count
        if "state.json" in str(dst):
            call_count += 1
            if call_count < 3:
                raise PermissionError("Simulated file lock")
        orig_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky_replace)
    saved = store.save(st)
    assert saved.is_file()
    assert call_count == 3
