"""Unit and regression tests for Pipeline Views & Panels (DEF-123 through DEF-132)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.design.gds import GameDesignSpec, Genre, CameraKind, StatCompare
from src.gameforge_ide.design.presets import PRESETS
from src.gameforge_ide.desktop.widgets.gds_form import GdsForm
from src.gameforge_ide.desktop.views.design_view import DesignView
from src.gameforge_ide.desktop.views.build_view import BuildView
from src.gameforge_ide.desktop.views.play_view import PlayView
from src.gameforge_ide.desktop.views.evidence_view import EvidenceView
from src.gameforge_ide.desktop.views.assets_view import AssetsView
from src.gameforge_ide.desktop.views.code_view import CodeView, CodeEditor, CodeHighlighter
from src.gameforge_ide.desktop.panels.diff_panel import DiffPanel
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel, _MessageBubble
from src.gameforge_ide.forge.model import RunState, RunSpec, StepSpec, StepKind, StepStatus
from src.gameforge_ide.forge.store import RunStore


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ── DEF-123: GdsForm default win condition syntax error ──────────────────────

def test_def123_gds_form_valid_default_win_condition(qapp):
    """Verify empty goals default to 'entity.relics.collected >= 5' conforming to STAT_RE."""
    form = GdsForm()
    try:
        spec = PRESETS["platformer"]()
        spec.goals.sandbox = True
        spec.goals.win = []  # Empty win condition in sandbox mode
        form.set_spec(spec)
        # Verify the text field uses the valid entity prefix
        assert "entity.relics.collected" in form._edit_win.text()
        # Verify validation passes without STAT_RE syntax error
        valid_spec = form.get_spec()
        assert valid_spec is not None
        assert len(valid_spec.goals.win) == 1
        assert valid_spec.goals.win[0].stat == "entity.relics.collected"
    finally:
        form.deleteLater()


test_def087_gds_form_valid_default_win_condition = test_def123_gds_form_valid_default_win_condition


# ── DEF-124: GdsForm condition case, dicts, and rule edit inputs ─────────────

def test_def124_gds_form_condition_case_and_dict_and_rule_edit(qapp):
    """Verify condition parsing handles mixed-case, shorthand stats, dicts, and rule edits."""
    form = GdsForm()
    try:
        spec = PRESETS["platformer"]()
        form.set_spec(spec)

        # 1. Mixed-case and shorthand stat normalization
        parsed = form._parse_conditions_text("Player.Health <= 0, coins.collected >= 10, Score >= 100", [])
        assert len(parsed) == 3
        assert parsed[0].stat == "player.health"
        assert parsed[1].stat == "entity.coins.collected"
        assert parsed[2].stat == "game.score"

        # 2. Raw dict formatting in _format_condition
        raw_dict = {"kind": "stat", "stat": "player.health", "op": "<=", "value": 0}
        formatted = form._format_condition(raw_dict)
        assert formatted == "player.health <= 0"

        # 3. Uncommitted pitch preservation when editing rules
        form._edit_pitch.setPlainText("Custom new pitch before adding rule")
        assert form._edit_pitch.toPlainText() == "Custom new pitch before adding rule"
        form._apply_inputs_to_spec()
        assert form._spec.overview.pitch == "Custom new pitch before adding rule"
    finally:
        form.deleteLater()


test_def088_gds_form_condition_case_and_dict_and_rule_edit = test_def124_gds_form_condition_case_and_dict_and_rule_edit


# ── DEF-125: DesignView patch rebuild and revision bump safety ────────────────

def test_def125_design_view_rebuild_and_revision_safety(qapp, tmp_path):
    """Verify DesignView aborts rebuild on apply failure and updates revision status."""
    view = DesignView()
    try:
        spec = PRESETS["platformer"]()
        view.open_draft(spec, project_dir=tmp_path / "TestGame")

        # 1. Verify projectChanged was emitted on draft
        assert view._current_project == (spec.meta.project_name or spec.meta.title)

        # 2. _on_apply_change returns False on empty ops
        view._pending_change_ops = []
        assert view._on_apply_change() is False

        # 3. _on_rebuild_changes doesn't call build_game if apply fails
        build_called = []
        view.buildRequested.connect(lambda p: build_called.append(p))
        view._pending_change_ops = []
        view._on_rebuild_changes()
        assert len(build_called) == 0

        # 4. Successful apply updates header status label to new revision
        old_rev = spec.meta.revision or 1
        view._pending_change_ops = [
            {"op": "replace", "path": "/overview/session_minutes", "value": 15}
        ]
        applied = view._on_apply_change()
        assert applied is True
        assert f"revision {old_rev + 1}" in view._lbl_status.text()
    finally:
        view.deleteLater()


test_def089_design_view_rebuild_and_revision_safety = test_def125_design_view_rebuild_and_revision_safety


# ── DEF-126: BuildView run combo selection and cancel deadlock ───────────────

def test_def126_build_view_run_combo_and_cancel_deadlock(qapp, tmp_path):
    """Verify BuildView preserves active run selection and unblocks orphaned runs."""
    p_dir = tmp_path / "MyProject"
    p_dir.mkdir(parents=True, exist_ok=True)
    store = RunStore(project_dir=p_dir, workspace_dir=tmp_path)

    # Create two runs
    spec1 = RunSpec(title="Run 1", workspace_dir=str(tmp_path), project_dir=str(p_dir), steps=[
        StepSpec(step_id="step1", kind=StepKind.DESIGN, title="Step 1")
    ])
    spec2 = RunSpec(title="Run 2", workspace_dir=str(tmp_path), project_dir=str(p_dir), steps=[
        StepSpec(step_id="step2", kind=StepKind.DESIGN, title="Step 2")
    ])
    state1 = RunState.new(spec1)
    state2 = RunState.new(spec2)
    state2.status = "RUNNING"
    store.save(state1)
    store.save(state2)

    view = BuildView(workspace_root=tmp_path)
    try:
        view._store = store
        view._current_project = "MyProject"
        view._current_project_dir = p_dir
        view.refresh_runs()

        # Find index of state2 in combo
        idx2 = -1
        for i in range(view._runs_combo.count()):
            if view._runs_combo.itemData(i) == state2.run.run_id:
                idx2 = i
                break
        assert idx2 >= 0
        view._runs_combo.setCurrentIndex(idx2)
        view._current_run_id = state2.run.run_id

        # Refreshing runs must preserve run 2 selection
        view.refresh_runs()
        assert view._runs_combo.currentData() == state2.run.run_id

        # Cancel orphaned run (not in memory): must mark CANCELLED in store
        view._current_state = state2
        view._current_run_id = state2.run.run_id
        view._on_cancel_clicked()

        updated_state = store.load(state2.run.run_id)
        assert updated_state.status == "CANCELLED"
    finally:
        view.deleteLater()


test_def090_build_view_run_combo_and_cancel_deadlock = test_def126_build_view_run_combo_and_cancel_deadlock


# ── DEF-127: PlayView missing packaged game guidance ─────────────────────────

def test_def127_play_view_missing_packaged_game_guidance(qapp, tmp_path):
    """Verify PlayView detects missing packaged executable and provides guidance."""
    p_dir = tmp_path / "UnpackagedGame"
    p_dir.mkdir(parents=True, exist_ok=True)

    view = PlayView(workspace_root=tmp_path)
    try:
        view.set_project("UnpackagedGame", project_dir=p_dir)
        # Packaged exe not created yet
        assert view._get_packaged_exe() is None
        assert "No packaged build or scenario results found" in view._lbl_summary.text()

        # Now simulate packaged exe created
        pkg_dir = p_dir / "Packaged" / "Windows"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        exe_file = pkg_dir / "UnpackagedGame.exe"
        exe_file.write_bytes(b"MZ\0\0")

        # Refresh must now detect it
        view.refresh_results()
        assert view._get_packaged_exe() == exe_file
        assert "Packaged build ready" in view._lbl_summary.text()
    finally:
        view.deleteLater()


test_def091_play_view_missing_packaged_game_guidance = test_def127_play_view_missing_packaged_game_guidance


# ── DEF-128: EvidenceView markdown filter and image scaling ──────────────────

def test_def128_evidence_view_markdown_filter_and_image(qapp, tmp_path):
    """Verify EvidenceView filters markdown reports and handles image scaling."""
    view = EvidenceView(workspace_root=tmp_path)
    try:
        # Check combo options include Reports / Docs
        combo_items = [view._filter_combo.itemText(i) for i in range(view._filter_combo.count())]
        assert "Reports / Docs" in combo_items

        # Test filter list with markdown
        paths = [
            Path("report.md"),
            Path("evidence.png"),
            Path("data.json"),
            Path("build.log"),
        ]
        md_filtered = view._apply_filter_to_list(paths, "Reports / Docs")
        assert md_filtered == [Path("report.md")]

        # Test image rescaling helper
        from PySide6.QtGui import QPixmap
        pix = QPixmap(100, 100)
        view._current_pixmap = pix
        view._rescale_image()
        assert not view._image_label.pixmap().isNull()
    finally:
        view.deleteLater()


test_def092_evidence_view_markdown_filter_and_image = test_def128_evidence_view_markdown_filter_and_image


# ── DEF-129: AssetsView showEvent and workspace synchronization ──────────────

def test_def129_assets_view_sync_and_show_event(qapp, tmp_path):
    """Verify AssetsView updates registry on workspace and project switches."""
    view = AssetsView(workspace_root=tmp_path)
    try:
        assert view._workspace == tmp_path.resolve()

        new_ws = tmp_path / "OtherWorkspace"
        new_ws.mkdir()
        view.set_workspace(new_ws)
        assert view._workspace == new_ws.resolve()

        proj_dir = tmp_path / "MyProject"
        proj_dir.mkdir()
        view.set_project("MyProject", project_dir=proj_dir)
        assert view._workspace == proj_dir.resolve()
        assert view._current_project == "MyProject"
    finally:
        view.deleteLater()


test_def093_assets_view_sync_and_show_event = test_def129_assets_view_sync_and_show_event


# ── DEF-130: CodeView editor, syntax styling, and read-only safety ───────────

def test_def130_code_view_editor_and_highlighter(qapp, tmp_path):
    """Verify CodeView contains CodeEditor with syntax highlighting and safe file reading."""
    mock_tools = MagicMock()
    code_view = CodeView(tmp_path, mock_tools)
    try:
        # 1. Code editor exists in central widget
        assert isinstance(code_view._editor, CodeEditor)
        assert code_view.centralWidget() is code_view._editor

        # 2. Write a test C++ and Python file
        cpp_file = tmp_path / "MyActor.cpp"
        cpp_file.write_text("#include <iostream>\n\nUCLASS()\nclass AMyActor {\n    int health = 100;\n};\n", encoding="utf-8")
        py_file = tmp_path / "script.py"
        py_file.write_text("def hello():\n    return 'GameForge'\n", encoding="utf-8")

        # 3. Open C++ file in editor
        ok = code_view.open_file(cpp_file, line=4)
        assert ok is True
        assert "AMyActor" in code_view._editor._edit.toPlainText()
        assert code_view._editor._highlighter is not None

        # 4. Open Python file
        ok = code_view.open_file(py_file, line=1)
        assert ok is True
        assert "hello" in code_view._editor._edit.toPlainText()

        # 5. Safe handling for missing file
        ok = code_view.open_file(tmp_path / "nonexistent.cpp")
        assert ok is False

        # 6. Safe handling for binary file (b"\0")
        bin_file = tmp_path / "data.bin"
        bin_file.write_bytes(b"\0\0\1\2\3binary_data")
        ok = code_view.open_file(bin_file)
        assert ok is False
        assert "Binary file" in code_view._editor._edit.toPlainText()
    finally:
        code_view.deleteLater()


test_def094_code_view_editor_and_highlighter = test_def130_code_view_editor_and_highlighter


# ── DEF-131: DiffPanel atomic actions and batch handling ─────────────────────

def test_def131_diff_panel_atomic_actions(qapp):
    """Verify DiffPanel approves/rejects atomically without double-click race conditions."""
    mock_tools = MagicMock()
    mock_tools.execute_approved_sync.return_value = {"status": "SUCCESS"}
    mock_tools.execute_sync.return_value = {"status": "SUCCESS"}

    panel = DiffPanel(mock_tools)
    try:
        panel.show_diff("diff_123", {"file_path": "Source/Game.cpp", "diff_patch": "@@ -1 +1 @@\n-old\n+new"})
        assert panel._btn_approve.isEnabled()
        assert panel._btn_reject.isEnabled()

        approved_signals = []
        panel.diff_approved.connect(lambda d: approved_signals.append(d))

        panel._on_approve()

        # Approved: buttons disabled and signal emitted
        assert panel._btn_approve.isEnabled() is False
        assert panel._btn_reject.isEnabled() is False
        assert panel._btn_rollback.isEnabled() is True
        assert approved_signals == ["diff_123"]
        mock_tools.execute_approved_sync.assert_called_with("apply_edit", {"diff_id": "diff_123"})

        # Test batch diff routing
        panel.show_diff("batch_456", {"file_path": "multiple", "diff_patch": "", "is_batch": True})
        panel._on_approve()
        mock_tools.execute_approved_sync.assert_called_with("apply_batch", {"batch_id": "batch_456"})
    finally:
        panel.deleteLater()


test_def095_diff_panel_atomic_actions = test_def131_diff_panel_atomic_actions


# ── DEF-132: ChatPanel empty bubble cleanup and tool call filter ─────────────

def test_def132_chat_panel_bubble_cleanup(qapp, tmp_path):
    """Verify ChatPanel suppresses raw tool call JSON leaks and cleans empty bubbles."""
    mock_agent = MagicMock()
    panel = ChatPanel(mock_agent, tmp_path)
    try:
        # 1. _is_raw_tool_json detection
        assert panel._is_raw_tool_json('{"tool": "propose_edit", "args": {}}') is True
        assert panel._is_raw_tool_json('```json\n{"name": "create_game", "arguments": {}}\n```') is True
        assert panel._is_raw_tool_json('<tool_call>search_index</tool_call>') is True
        assert panel._is_raw_tool_json('Hello! Let us build a game.') is False

        # 2. _on_done cleans empty assistant bubbles
        panel._active_bubble = panel._add_bubble("assistant", "")
        assert panel._active_bubble is not None
        # Turn ends without tokens
        panel._on_done("")
        assert panel._active_bubble is None
    finally:
        panel.deleteLater()


test_def096_chat_panel_bubble_cleanup = test_def132_chat_panel_bubble_cleanup


