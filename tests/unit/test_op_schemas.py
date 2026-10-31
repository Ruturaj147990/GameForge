"""P0 WI-0.8 (AD-14): op argument schemas."""
import subprocess
import sys
from pathlib import Path

from src.gameforge_ide.unreal import op_catalog, op_schemas

REPO = Path(__file__).resolve().parents[2]


def test_every_schema_is_a_catalogued_op_and_every_op_has_one():
    assert set(op_schemas.SCHEMAS) == set(op_catalog.CATALOG)


def test_unknown_key_rejected_for_reviewed_op():
    clean, errs = op_schemas.validate_args("spawn_actor", {"label": "A", "bogus": 1})
    assert clean is None and any("bogus" in e for e in errs)


def test_valid_call_round_trips_only_set_keys():
    clean, errs = op_schemas.validate_args("spawn_actor", {"label": "A", "location": {"x": 1, "y": 2, "z": 3}})
    assert errs == [] and clean == {"label": "A", "location": {"x": 1.0, "y": 2.0, "z": 3.0}}


def test_wrong_type_rejected():
    clean, errs = op_schemas.validate_args("new_level", {"level_path": "not/a/game/path"})
    assert clean is None and errs


def test_strict_mode_requires_a_schema():
    assert op_schemas.validate_args("no_such_op", {}, strict=True)[0] is None
    assert op_schemas.validate_args("no_such_op", {"a": 1})[0] == {"a": 1}


def test_gateway_refuses_invalid_args_without_an_editor(tmp_path):
    from src.gameforge_ide.backend.tools.game_tools import GameTools
    up = tmp_path / "P.uproject"
    up.write_text("{}", encoding="utf-8")
    res = GameTools(tmp_path).unreal_editor(str(up), "spawn_actor", {"bogus": True})
    assert res["status"] == "ERROR" and res["error"] == "invalid args for op"


def test_generated_drafts_are_current():
    r = subprocess.run([sys.executable, str(REPO / "scripts/tools/gen_op_schemas.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "126 ops" in r.stdout
