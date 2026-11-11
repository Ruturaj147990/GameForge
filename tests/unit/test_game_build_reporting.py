"""Game-build reporting: failures are reported truthfully, stage progress is streamed, and the
chat renders RUNNING progress items."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.models.modes import AutonomyProfile, TaskMode
from src.gameforge_ide.backend.providers.router import ModelRouter
from src.gameforge_ide.backend.session_manager import SessionManager


def _runtime(ws: Path) -> AgentRuntime:
    db = ws / ".gameforge" / "sessions.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    return AgentRuntime(ws, SessionManager(db), ModelRouter())


def _run_fast_create(ws: Path, outcome: dict, emit_stages: bool = False):
    p_dir = Path(outcome.get("project_dir", ws / "P"))
    if outcome.get("ok"):
        p_dir.mkdir(parents=True, exist_ok=True)
        (p_dir / "Source").mkdir(parents=True, exist_ok=True)
        (p_dir / "Config").mkdir(parents=True, exist_ok=True)
        (p_dir / "P.uproject").write_text("{}", encoding="utf-8")
        (p_dir / "Source" / "Game.cpp").write_text("// C++ Tactical Shooter logic\nvoid AWeapon::Fire() {}\n", encoding="utf-8")

    rt = _runtime(ws)
    sess = rt.session_manager.create_session(
        name="t", model_name="gameforge-qwen3.5-9b", provider_type="ollama",
        task_mode=TaskMode.FAST, autonomy_profile=AutonomyProfile.AGENTIC,
    )

    def fake_create_game(**kw):
        cb = kw.get("on_event")
        if emit_stages and cb:
            cb("stage_started", {"stage": "scaffold", "step_id": "scaffold"})
            cb("stage_finished", {"stage": "scaffold", "step_id": "scaffold", "ok": True, "duration_s": 1.5})
            cb("stage_started", {"stage": "build_editor", "step_id": "build"})
            cb("stage_finished", {"stage": "build_editor", "step_id": "build", "ok": False, "duration_s": 3.0,
                                  "errors": ["C2065: undeclared identifier"]})
        return outcome

    async def go():
        evs = []
        with patch.object(rt, "_is_game_creation_request", return_value=True), \
             patch.object(rt.tool_gateway.game_tools, "create_game", side_effect=fake_create_game), \
             patch("src.gameforge_ide.design.prompt_to_gds.prompt_to_gds", side_effect=RuntimeError("offline")):
            async for ev in rt.execute_task_stream(sess.session_id, "make a tactical shooter game"):
                evs.append(ev)
        return evs

    return asyncio.run(go())


def test_failed_build_is_reported_as_failure_not_success(tmp_path):
    evs = _run_fast_create(tmp_path, {
        "status": "FAILED", "ok": False, "project_dir": str(tmp_path / "P"),
        "failed_stage": "build", "error": "UBT exited with code 6", "run_id": "run_x",
        "stages": [{"step_id": "scaffold", "status": "DONE"}, {"step_id": "build", "status": "FAILED"}],
    }, emit_stages=True)
    done = [e for e in evs if e.event_type == "done"]
    assert done, [e.event_type for e in evs]
    text = done[-1].content
    assert "did **not** complete" in text and "build" in text and "UBT exited with code 6" in text
    assert "complete and verified" not in text
    assert done[-1].metadata.get("terminal_status") == "FAILED"


def test_stage_progress_is_streamed_as_running_status(tmp_path):
    evs = _run_fast_create(tmp_path, {"status": "SUCCESS", "ok": True, "project_dir": str(tmp_path / "P"),
                                      "exe": str(tmp_path / "P" / "Game.exe")}, emit_stages=True)
    running = [e for e in evs if e.event_type == "status" and e.content == "RUNNING"]
    msgs = " | ".join(str(e.metadata.get("message")) for e in running)
    assert "scaffold" in msgs and "failed" in msgs
    done = [e for e in evs if e.event_type == "done"][-1]
    assert "complete and verified" in done.content and "Game.exe" in done.content


def test_running_status_item_renders_stage_message(tmp_path):
    from PySide6.QtWidgets import QApplication
    from src.gameforge_ide.desktop.panels.activity_card import StatusActivityItem

    QApplication.instance() or QApplication([])
    item = StatusActivityItem("running", {"stage": "Build Editor", "message": "Running build editor..."})
    assert "Running build editor" in item._raw_text
    item.meta.update({"ok": False, "message": "build editor failed (3.0s)"})
    item._refresh_display()
    assert "failed" in item._raw_text and "⚠" in item._raw_text
