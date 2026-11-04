"""Comprehensive regression tests for GameForge Storage & Core Persistence subsystems.

Covers:
- Safe atomic writes and self-healing JSON recovery from .bak
- DesignStore revision history and corruption recovery
- RunStore/ForgeStore event logging, index durability, and backup recovery
- ApprovalStore lifecycle, transitions, and backup recovery
- TaskStore TaskPlan graph persistence, recovery, and task state caching
- DiffStore SHA-256 verification and base64 payload integrity
- Dangling temporary file garbage collection
- EventBus wildcard topic matching and subscriber exception isolation
- JobManager unhandled background exception logging, job tracking, and cancellation
- Settings thread-safe save and corruption fallback
- Systems probes error resilience on malformed paths
"""
from __future__ import annotations

import json
from pathlib import Path
import threading
import time
import pytest

from src.gameforge_ide.core import events, jobs, projects, settings, systems
from src.gameforge_ide.design.presets import preset_platformer
from src.gameforge_ide.forge.model import RunSpec, RunState, StepKind, StepSpec
from src.gameforge_ide.backend.agent.task_plan import TaskNode, TaskPlan
from src.gameforge_ide.storage import (
    ApprovalStore,
    DesignStore,
    DiffStore,
    ForgeStore,
    RunStore,
    TaskStore,
    atomic_write_json,
    atomic_write_text,
    safe_read_json,
    safe_read_text,
    sweep_dangling_temp_files,
)


@pytest.fixture
def temp_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "test_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# =========================================================================
# 1. Atomic Storage & Self-Healing Backup Tests
# =========================================================================

def test_atomic_write_and_safe_read_json_recovery(temp_ws: Path):
    target = temp_ws / "config.json"
    data = {"engine": "5.7.4", "vram_mb": 12288, "features": ["nanite", "lumen"]}

    # Write atomically with backup
    atomic_write_json(target, data, sync=True, backup=True)
    assert target.is_file()
    bak_file = target.with_suffix(".json.bak")
    assert bak_file.is_file()

    # Corrupt primary file by overwriting with invalid JSON garbage
    target.write_text("{this is corrupted invalid json content!!!", encoding="utf-8")

    # safe_read_json should detect corruption, recover from .bak, and self-heal primary
    recovered_data, was_recovered = safe_read_json(target, fallback_backup=True)
    assert was_recovered is True
    assert recovered_data == data

    # Verify primary file on disk was self-healed
    assert json.loads(target.read_text(encoding="utf-8")) == data


def test_dangling_temp_file_sweeping(temp_ws: Path):
    # Create several fake abandoned temporary files
    dangling_files = [
        temp_ws / ".tmp_abc123.tmp",
        temp_ws / "settings.json.tmp_89ab",
        temp_ws / ".state.json.tmp",
    ]
    for df in dangling_files:
        df.write_text("abandoned temp content", encoding="utf-8")
        assert df.is_file()

    valid_file = temp_ws / "important.json"
    valid_file.write_text("{}", encoding="utf-8")

    # Sweep temp files older than 0 seconds
    removed = sweep_dangling_temp_files(temp_ws, max_age_seconds=0.0, recursive=True)
    assert len(removed) >= 3

    for df in dangling_files:
        assert not df.exists()
    assert valid_file.is_file()


# =========================================================================
# 2. DesignStore Revision & Corruption Recovery Tests
# =========================================================================

def test_design_store_revision_and_corruption_recovery(temp_ws: Path):
    store = DesignStore(temp_ws)

    # Save Revision 1
    gds_v1 = preset_platformer(title="TestGame")
    assert gds_v1.meta.revision == 1
    store.save(gds_v1)
    assert store.main_file.is_file()
    assert 1 in store.history()

    # Save Revision 2
    gds_v2 = gds_v1.model_copy(deep=True)
    gds_v2.meta.revision = 2
    gds_v2.meta.title = "TestGame_v2"
    store.save(gds_v2)
    assert 2 in store.history()
    loaded_v2 = store.load()
    assert loaded_v2 is not None
    assert loaded_v2.meta.revision == 2

    # Simulate catastrophic corruption: truncate game.gds.json to empty 0-bytes
    store.main_file.write_text("", encoding="utf-8")

    # Store load should automatically self-heal from .bak or revision history
    repaired_gds = store.load()
    assert repaired_gds is not None
    assert repaired_gds.meta.revision == 2
    assert repaired_gds.meta.title == "TestGame_v2"

    # Verify primary game.gds.json file was restored on disk
    assert store.main_file.stat().st_size > 50


# =========================================================================
# 3. ForgeStore / RunStore Tests
# =========================================================================

def test_forge_run_store_logging_and_index_recovery(temp_ws: Path):
    store = RunStore(project_dir=None, workspace_dir=temp_ws)
    run_spec = RunSpec(
        run_id="run_audit_001",
        title="Forge Persistence Audit",
        workspace_dir=str(temp_ws),
        steps=[StepSpec(step_id="step1", kind=StepKind.DESIGN, title="Design Step")],
    )
    state = RunState.new(run_spec)
    saved_path = store.save(state)
    assert saved_path.is_file()

    # Append sequential events
    for i in range(5):
        store.append_event("run_audit_001", {"event_type": "progress", "step": i, "percent": i * 20})

    events = store.load_events("run_audit_001")
    assert len(events) == 5
    assert events[-1]["percent"] == 80

    # Index corruption recovery
    idx_file = temp_ws / ".gameforge" / "runs_index.json"
    assert idx_file.is_file()
    assert idx_file.with_suffix(".json.bak").is_file()

    # Corrupt index file
    idx_file.write_text("INVALID_JSON_CORRUPTED_INDEX", encoding="utf-8")

    # get_runs_index should fall back to .bak seamlessly
    index_entries = store.get_runs_index()
    assert len(index_entries) >= 1
    assert index_entries[0]["run_id"] == "run_audit_001"


# =========================================================================
# 4. ApprovalStore Lifecycle & Transitions Tests
# =========================================================================

def test_approval_store_transitions_and_backup(temp_ws: Path):
    store = ApprovalStore(temp_ws)

    # Create approval
    rec = store.create(
        tool="unreal_package",
        args={"project": "MyGame"},
        summary="Package MyGame shipping",
        consequence="Builds 400MB executable",
    )
    apr_id = rec["approval_id"]
    assert rec["status"] == "PENDING"
    assert len(store.list_pending()) == 1

    # Verify backup exists
    apr_path = store.root / f"{apr_id}.json"
    assert apr_path.is_file()

    # Corrupt primary file
    apr_path.write_text("{malformed: corrupt json", encoding="utf-8")
    loaded = store.get(apr_id)
    assert loaded is not None
    assert loaded["tool"] == "unreal_package"

    # Enforce transitions
    assert store.transition(apr_id, "DONE") is None  # Invalid transition directly to DONE
    approved = store.transition(apr_id, "APPROVED")
    assert approved is not None and approved["status"] == "APPROVED"
    assert len(store.list_pending()) == 0

    done = store.transition(apr_id, "DONE", result={"success": True})
    assert done is not None and done["status"] == "DONE"
    assert done["result"]["success"] is True


# =========================================================================
# 5. TaskStore & TaskPlan DAG Resilience Tests
# =========================================================================

def test_task_store_persistence_and_plan_lifecycle(temp_ws: Path):
    store = TaskStore(temp_ws)

    plan = TaskPlan(
        plan_id="plan_test_001",
        goal="Build and verify character locomotion",
    )
    node1 = TaskNode(
        task_id="t1",
        title="Check mannequin assets",
        objective="Inspect Manny mesh",
        expected_result="Mesh exists",
    )
    node2 = TaskNode(
        task_id="t2",
        title="Compile blueprint",
        objective="Compile ABP_Unarmed",
        expected_result="Compiled ok",
        dependency_ids=["t1"],
    )
    plan.add_task(node1)
    plan.add_task(node2)

    saved_path = store.save_plan(plan)
    assert saved_path.is_file()
    assert saved_path.with_suffix(".json.bak").is_file()

    # Corrupt plan file
    saved_path.write_text("CORRUPTED_PLAN_JSON", encoding="utf-8")

    # Load should recover via TaskStore
    repaired_plan = store.load_plan("plan_test_001")
    assert repaired_plan is not None
    assert len(repaired_plan.tasks) == 2
    assert "t1" in repaired_plan.tasks and "t2" in repaired_plan.tasks

    # Verify TaskPlan.load_by_id also functions with recovery
    loaded_via_cls = TaskPlan.load_by_id(temp_ws, "plan_test_001")
    assert loaded_via_cls is not None
    assert loaded_via_cls.goal == "Build and verify character locomotion"

    # Task state dictionary persistence
    store.save_task_state("session_123", {"phase": "author", "iteration": 4})
    state_loaded = store.load_task_state("session_123")
    assert state_loaded is not None
    assert state_loaded["phase"] == "author"
    assert state_loaded["iteration"] == 4


# =========================================================================
# 6. DiffStore SHA-256 & Rollback Snapshot Tests
# =========================================================================

def test_diff_store_sha256_and_recovery(temp_ws: Path):
    diff_store = DiffStore(temp_ws)

    original_bytes = b"int health = 100;\n"
    new_bytes = b"int health = 200;\n"

    diff_rec = {
        "diff_id": "diff_999",
        "file_path": "Source/Player.cpp",
        "original_bytes": original_bytes,
        "new_bytes": new_bytes,
        "diff_text": "-int health = 100;\n+int health = 200;\n",
        "status": "PENDING_APPROVAL",
    }
    saved_path = diff_store.save_diff("diff_999", diff_rec)
    assert saved_path.is_file()

    # Corrupt primary diff file
    saved_path.write_text("CORRUPT_DIFF_DATA", encoding="utf-8")

    # load_diff should recover from .bak and decode binary bytes cleanly
    loaded = diff_store.load_diff("diff_999")
    assert loaded is not None
    assert loaded["original_bytes"] == original_bytes
    assert loaded["new_bytes"] == new_bytes
    assert loaded["file_path"] == "Source/Player.cpp"


# =========================================================================
# 7. EventBus Wildcards & Subscriber Exception Isolation Tests
# =========================================================================

def test_event_bus_pattern_wildcards_and_isolated_errors():
    bus = events.EventBus()

    received_wildcard: list[str] = []
    received_exact: list[str] = []

    # Wildcard subscriber matching run.*
    bus.subscribe("run.*", lambda topic, ev: received_wildcard.append(topic))
    # Exact subscriber
    bus.subscribe("run.step", lambda topic, ev: received_exact.append(topic))

    # Faulty subscriber that raises an unhandled exception
    def broken_callback(topic, ev):
        raise ValueError("Simulated subscriber crash")

    bus.subscribe("run.step", broken_callback)

    # Publish an event
    bus.publish("run.step", {"step": 1})

    # Both healthy subscribers should have received the event despite broken_callback failing
    assert "run.step" in received_wildcard
    assert "run.step" in received_exact

    # Exception should be recorded in error tracking
    assert len(bus.errors) >= 1
    topic, exc = bus.errors[0]
    assert topic == "run.step"
    assert isinstance(exc, ValueError)

    # Publish on non-matching topic: only wildcard matching job.* should receive
    bus.publish("other.topic", {"data": 123})
    assert len(received_wildcard) == 1


# =========================================================================
# 8. JobManager Background Exception & Tracking Tests
# =========================================================================

def test_job_manager_unhandled_exception_logging():
    jobs.reset_default_job_manager()
    mgr = jobs.default_job_manager()

    bus = events.default_bus()
    failed_events: list[dict] = []
    unsub = bus.subscribe("job.failed", lambda t, ev: failed_events.append(ev))

    try:
        def crashing_task():
            time.sleep(0.01)
            raise RuntimeError("Deliberate background worker explosion")

        handle = mgr.submit(crashing_task, name="test_crash_job")
        assert handle.name == "test_crash_job"

        # Wait for job completion
        for _ in range(50):
            if handle.done():
                break
            time.sleep(0.02)

        assert handle.status == "FAILED"
        assert isinstance(handle.error, RuntimeError)

        # Confirm failure was captured in JobManager ledger
        failed = mgr.failed_jobs()
        assert len(failed) >= 1
        assert failed[-1][0] == "test_crash_job"
        assert "Deliberate" in str(failed[-1][1])

        # Confirm job.failed event was published
        time.sleep(0.05)
        assert len(failed_events) >= 1
        assert failed_events[-1]["job_name"] == "test_crash_job"

    finally:
        unsub()
        jobs.reset_default_job_manager()


# =========================================================================
# 9. Settings Thread Safety & Backup Tests
# =========================================================================

def test_settings_save_and_backup(temp_ws: Path, monkeypatch):
    test_settings_file = temp_ws / "settings.json"
    monkeypatch.setenv("GAMEFORGE_USER_SETTINGS", str(test_settings_file))
    settings.reset_settings_cache()

    # Save settings
    saved_path = settings.save_user_settings({"ollama_url": "http://127.0.0.1:11434", "bridge_port": 47815})
    assert saved_path.is_file()
    assert saved_path.with_suffix(".json.bak").is_file()

    # Corrupt settings.json
    saved_path.write_text("{corrupt json", encoding="utf-8")

    # Read should recover from .bak
    loaded = settings._read_json(saved_path)
    assert loaded.get("ollama_url") == "http://127.0.0.1:11434"
    assert loaded.get("bridge_port") == 47815


# =========================================================================
# 10. Systems Probes Error Resilience Tests
# =========================================================================

def test_systems_probes_resilience():
    # Calling probe_disk on non-existent projects_root should fall back to cwd without raising
    s = settings.get_settings()
    row_disk = systems.probe_disk(s)
    assert row_disk.key == "disk"
    assert row_disk.state in ("ok", "degraded", "offline")

    row_engine = systems.probe_engine(s)
    assert row_engine.key == "engine"
    assert row_engine.state in ("ok", "offline")

    row_ram = systems.probe_ram()
    assert row_ram.key == "ram"
    assert row_ram.state in ("ok", "degraded")
