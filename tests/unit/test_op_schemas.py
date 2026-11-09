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


def test_all_thirty_reviewed_ops_reject_bogus_keys():
    assert len(op_schemas.REVIEWED) >= 33
    for op in op_schemas.REVIEWED:
        clean, errs = op_schemas.validate_args(op, {"completely_bogus_key_123": True})
        assert clean is None and errs, f"Op {op} should have rejected completely_bogus_key_123"


def test_reviewed_ops_valid_payloads_round_trip():
    # create_material
    clean, errs = op_schemas.validate_args("create_material", {
        "asset_path": "/Game/Materials/M_Test",
        "base_color": [1.0, 0.5, 0.0],
        "roughness": 0.2
    })
    assert errs == [] and clean["asset_path"] == "/Game/Materials/M_Test"
    assert clean["base_color"] == [1.0, 0.5, 0.0]

    # landscape_create
    clean, errs = op_schemas.validate_args("landscape_create", {
        "elevation_scale": 1500.0,
        "terrain_type": "Mountains"
    })
    assert errs == [] and clean["elevation_scale"] == 1500.0

    # nav_find_path
    clean, errs = op_schemas.validate_args("nav_find_path", {
        "start": {"x": 100, "y": 200, "z": 0},
        "end": {"x": 500, "y": 600, "z": 50}
    })
    assert errs == [] and clean["start"]["x"] == 100.0

    # viewport_screenshot
    clean, errs = op_schemas.validate_args("viewport_screenshot", {
        "output_path": "E:/temp/shot.png",
        "show_ui": True
    })
    assert errs == [] and clean["show_ui"] is True


def test_generated_drafts_are_current():
    r = subprocess.run([sys.executable, str(REPO / "scripts/tools/gen_op_schemas.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"{len(op_catalog.CATALOG)} ops" in r.stdout


def test_agent_ops_have_schemas_and_hosted_oneof(tmp_path):
    from src.gameforge_ide.backend.tools.gateway import ToolGateway
    gw = ToolGateway(tmp_path)
    hosted_defs = gw.get_definitions(for_hosted=True)
    unreal_def = next(d for d in hosted_defs if d.name == "unreal_editor")
    assert "oneOf" in unreal_def.parameters
    assert len(unreal_def.parameters["oneOf"]) == len(op_catalog.agent_ops())

    local_defs = gw.get_definitions(for_hosted=False)
    unreal_local = next(d for d in local_defs if d.name == "unreal_editor")
    assert "enum" in unreal_local.parameters["properties"]["op"]
