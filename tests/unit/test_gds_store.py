"""Unit tests for GDS disk storage, revision history, and structural diff (P1 WI-1.8)."""
from __future__ import annotations

from pathlib import Path
import pytest

from src.gameforge_ide.design.presets import preset_platformer
from src.gameforge_ide.design.store import (
    DESIGN_DIR,
    RevisionConflict,
    diff,
    history,
    load,
    save,
)


def test_save_and_load(tmp_path: Path):
    gds = preset_platformer(title="Test Platformer")
    assert gds.meta.revision == 1

    saved_path = save(tmp_path, gds)
    assert saved_path == tmp_path / DESIGN_DIR / "game.gds.json"
    assert saved_path.is_file()

    # Check history file
    hist_file = tmp_path / DESIGN_DIR / "history" / "r0001.gds.json"
    assert hist_file.is_file()

    # Check load
    loaded = load(tmp_path)
    assert loaded is not None
    assert loaded.meta.title == "Test Platformer"
    assert loaded.meta.revision == 1
    assert loaded.overview.genre == gds.overview.genre


def test_history_and_revision_advancement(tmp_path: Path):
    gds1 = preset_platformer(title="Revision 1")
    gds1.meta.revision = 1
    save(tmp_path, gds1)
    assert history(tmp_path) == [1]

    # Advance revision
    gds2 = gds1.model_copy(deep=True)
    gds2.meta.revision = 2
    save(tmp_path, gds2)
    assert history(tmp_path) == [1, 2]

    loaded = load(tmp_path)
    assert loaded is not None
    assert loaded.meta.revision == 2


def test_revision_conflict(tmp_path: Path):
    gds = preset_platformer()
    gds.meta.revision = 2
    save(tmp_path, gds)

    # Trying to save revision 2 again or revision 1 raises RevisionConflict
    with pytest.raises(RevisionConflict, match="stored revision is 2"):
        save(tmp_path, gds)

    gds_stale = gds.model_copy(deep=True)
    gds_stale.meta.revision = 1
    with pytest.raises(RevisionConflict):
        save(tmp_path, gds_stale)


def test_diff_structural():
    gds_a = preset_platformer(title="Version A")
    gds_b = gds_a.model_copy(deep=True)

    # Change count on first entity
    old_count = gds_a.entities[0].count
    new_count = old_count + 3
    gds_b.entities[0].count = new_count

    ops = diff(gds_a, gds_b)
    replace_ops = [op for op in ops if op.get("path") == "/entities/0/count"]
    assert len(replace_ops) == 1
    assert replace_ops[0]["op"] == "replace"
    assert replace_ops[0]["from"] == old_count
    assert replace_ops[0]["value"] == new_count
