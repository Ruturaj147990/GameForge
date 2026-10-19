"""Unit tests for task loading and schema normalization."""

import tempfile
from pathlib import Path
import pytest
from gameforge_bench.task_loader import load_task, load_task_inventory, normalize_task_dict


def test_load_valid_pilot_task():
    pilot_path = Path("pilot_tasks/t2-001-third-person-controller.yaml")
    assert pilot_path.is_file()

    task = load_task(pilot_path)
    assert task.id == "t2-001-third-person-controller"
    assert task.logical_task_id == "T2-001"
    assert task.tier == "T2"
    assert task.title == "Third-person movement and camera"
    assert task.limits.wall_clock_seconds == 2700
    assert task.limits.max_tool_calls == 120
    assert "project gameplay source paths" in task.allowed_edit_paths
    assert "tests" in task.forbidden_edits
    assert task.grading.build_required is True
    assert task.provenance.allowed_use_review_status == "pending"


def test_load_all_six_pilot_tasks():
    pilot_dir = Path("pilot_tasks")
    yamls = list(pilot_dir.glob("*.yaml"))
    assert len(yamls) == 6

    for y in yamls:
        t = load_task(y)
        assert t.id
        assert t.logical_task_id
        assert t.prompt
        assert t.limits.wall_clock_seconds > 0
        assert len(t.allowed_edit_paths) > 0


def test_load_task_inventory():
    inv_path = Path("TASK_INVENTORY.csv")
    tasks = load_task_inventory(inv_path)
    assert len(tasks) == 30

    ids = [t.id for t in tasks]
    assert len(ids) == len(set(ids)), "Task IDs in inventory must be unique"
    assert "T2-001" in ids
    assert "T3-030" in ids


def test_invalid_yaml_handling(tmp_path):
    bad_yaml = tmp_path / "corrupt.yaml"
    bad_yaml.write_text("id: [unclosed list\n  logical_task_id: T2-001", encoding="utf-8")

    with pytest.raises(Exception):
        load_task(bad_yaml)


def test_missing_required_fields_raises_validation_error(tmp_path):
    incomplete_yaml = tmp_path / "incomplete.yaml"
    # Missing prompt and limits
    incomplete_yaml.write_text("id: t1-001\ntitle: test", encoding="utf-8")

    with pytest.raises(Exception):
        load_task(incomplete_yaml)
