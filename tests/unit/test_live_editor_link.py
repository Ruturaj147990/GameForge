"""Offline tests for the real Unreal editor link (live_editor.py).

The live round trip against UE 5.7.4 is recorded separately in
E:\\GameForge\\validation\\live_editor_probe_20261027\\probe_result.json; these tests cover
the parts that do not need a running editor.
"""

import json
from pathlib import Path

import pytest

from src.gameforge_ide.unreal.live_editor import (
    OPS_LIBRARY_SOURCE,
    RESULT_SENTINEL,
    LiveEditorError,
    LiveEditorLink,
    build_command,
    load_engine_remote_execution,
    parse_result,
)


def _project(tmp_path: Path) -> Path:
    up = tmp_path / "Probe" / "Probe.uproject"
    up.parent.mkdir(parents=True)
    up.write_text(json.dumps({"FileVersion": 3, "EngineAssociation": "5.7", "Plugins": []}), encoding="utf-8")
    return up


def test_build_command_embeds_args_as_literal_not_code():
    hostile = {"label": "x'); import os; os.system('calc') #"}
    cmd = build_command("spawn_actor", hostile, "tok")
    lines = cmd.strip().splitlines()
    assert lines[0] == "import gameforge_ops"
    assert lines[1].startswith("gameforge_ops.dispatch(") and lines[1].endswith(")")
    literal = lines[1][len("gameforge_ops.dispatch("):-1]
    import ast
    payload = json.loads(ast.literal_eval(literal))  # must be a pure string literal
    assert payload == {"op": "spawn_actor", "args": hostile, "token": "tok"}


def test_parse_result_extracts_envelope_from_output():
    env = {"ok": True, "op": "handshake", "data": {"engine_version": "5.7.4"}}
    res = {"success": True, "result": "None",
           "output": [{"type": "Info", "output": "noise"},
                      {"type": "Info", "output": RESULT_SENTINEL + json.dumps(env)}]}
    assert parse_result(res) == env


def test_parse_result_fails_closed_without_envelope():
    res = {"success": False, "result": "Traceback ...", "output": [{"type": "Error", "output": "boom"}]}
    parsed = parse_result(res)
    assert parsed["ok"] is False
    assert "no GameForge result envelope" in parsed["errors"][0]


def test_parse_result_rejects_malformed_envelope():
    res = {"output": [{"output": RESULT_SENTINEL + "{not json"}]}
    assert parse_result(res)["ok"] is False


def test_prepare_project_enables_loopback_remote_exec_and_writes_token(tmp_path):
    link = LiveEditorLink(_project(tmp_path))
    info = link.prepare_project()
    ini = Path(info["config"]).read_text(encoding="utf-8")
    assert "bRemoteExecution=True" in ini
    assert "RemoteExecutionMulticastBindAddress=127.0.0.1" in ini
    assert "RemoteExecutionMulticastTtl=0" in ini
    deployed = Path(info["ops_library"])
    assert sorted(p.name for p in deployed.glob("*.py")) == sorted(p.name for p in OPS_LIBRARY_SOURCE.glob("*.py"))
    assert all((deployed / p.name).read_bytes() == p.read_bytes() for p in OPS_LIBRARY_SOURCE.glob("*.py"))
    assert len(link.token_file.read_text(encoding="utf-8").strip()) == 64
    plugins = {p["Name"] for p in json.loads(link.uproject.read_text(encoding="utf-8"))["Plugins"]}
    assert {"PythonScriptPlugin", "EditorScriptingUtilities"} <= plugins
    # idempotent: second prepare does not duplicate the settings block
    link.prepare_project()
    assert Path(info["config"]).read_text(encoding="utf-8").count("bRemoteExecution=True") == 1


def test_call_without_connection_fails_closed(tmp_path):
    link = LiveEditorLink(_project(tmp_path))
    res = link.call("actors_in_level", {})
    assert res["ok"] is False and res["errors"] == ["EDITOR_NOT_CONNECTED"]


def test_connect_without_token_is_refused(tmp_path):
    link = LiveEditorLink(_project(tmp_path))
    with pytest.raises(LiveEditorError, match="no session token"):
        link.connect(discovery_timeout_s=0.1)


def test_missing_engine_is_reported(tmp_path):
    with pytest.raises(LiveEditorError, match="remote_execution.py not found"):
        load_engine_remote_execution(tmp_path)


def test_ops_library_declares_token_check_and_sentinel():
    src = (OPS_LIBRARY_SOURCE / "_core.py").read_text(encoding="utf-8")
    assert RESULT_SENTINEL in src
    assert "_check_token(req.get(\"token\"))" in src
    assert "hmac.compare_digest" in src
