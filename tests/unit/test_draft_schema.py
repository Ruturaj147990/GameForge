"""Unit tests for DesignDraft schema (P1 WI-1.3)."""
from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from src.gameforge_ide.design.draft import DesignDraft, DraftEntity, DraftWin
from src.gameforge_ide.design.gds import CameraKind, EntityKind, Genre


def _make_valid_draft(**kwargs) -> DesignDraft:
    data = {
        "title": "Platformer Rush",
        "genre": Genre.PLATFORMER,
        "camera": CameraKind.SIDE_SCROLLER,
        "pitch": "Jump across platforms to collect coins",
        "entities": [
            {"kind": EntityKind.PLAYER, "count": 1, "note": "Main player"},
            {"kind": EntityKind.PICKUP, "count": 10, "note": "Gold coins"},
        ],
        "win": [{"type": "collect_all"}],
        "lose": [{"type": "fall_off"}],
    }
    data.update(kwargs)
    return DesignDraft.model_validate(data)


def test_valid_draft_round_trips():
    draft = _make_valid_draft()
    dumped = draft.model_dump_json()
    reloaded = DesignDraft.model_validate_json(dumped)
    assert reloaded.title == "Platformer Rush"
    assert reloaded.genre == Genre.PLATFORMER
    assert len(reloaded.entities) == 2
    assert reloaded.win[0].type == "collect_all"
    assert reloaded == draft


def test_draft_extra_fields_forbidden():
    with pytest.raises(ValidationError, match="extra"):
        _make_valid_draft(unexpected_extra_field="invalid")


def test_draft_requires_at_least_one_win_condition():
    with pytest.raises(ValidationError):
        _make_valid_draft(win=[])


def test_draft_json_schema_compact():
    schema = DesignDraft.model_json_schema()
    schema_str = json.dumps(schema)
    size_kb = len(schema_str.encode("utf-8")) / 1024
    assert size_kb <= 6.0, f"DesignDraft schema is {size_kb:.1f} KB, expected <= 6 KB"
