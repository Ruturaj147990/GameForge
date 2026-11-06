"""Comprehensive PySide6 UI Component Unit Tests for GameForge 1.0.

Conforms to GameForge 1.0 Master Transformation Directive:
- Tests all newly implemented and refactored UI components in isolation (headless offscreen).
- Verifies TopBar exposes task_mode_combo ('Planning', 'Fast') and autonomy_combo
  ('Manual', 'Auto-Edit', 'Agentic'), emits taskModeChanged/autonomyProfileChanged,
  and supports set_task_mode / set_autonomy_profile.
- Verifies ChatPanel exposes task_mode_combo and autonomy_combo, emits task_mode_changed
  and autonomy_changed, and syncs session modes in SessionManager.
- Verifies PlanCard (desktop/panels/plan_card.py) renders goal titles, version badges,
  status badges, approach summary, step checklist with status icons (STEP_STATUS_ICONS),
  prominent active 'Proceed' QPushButton, and inline revision input (txt_revision, btn_revise).
- Verifies DiffApprovalCard (desktop/panels/diff_card.py) in Manual profile renders
  Approve/Reject controls, diff patch preview, and emits diff_approved / diff_rejected.
- Verifies FileChangedNotification (desktop/panels/diff_card.py) provides non-blocking
  mutation notices in Auto-Edit and Agentic profiles.
- Verifies Rail (desktop/shell/rail.py) has retired separate Design and Build buttons
  from primary RAIL_ITEMS (rail.button('design') is None, rail.button('build') is None).
- Verifies bidirectional mode/autonomy signal wiring between TopBar and ChatPanel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from src.gameforge_ide.backend.models.modes import AutonomyProfile, TaskMode
from src.gameforge_ide.backend.models.plan_artifact import PlanArtifact, PlanStep
from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.desktop.panels.approval_card import ApprovalCard
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel, _MessageBubble
from src.gameforge_ide.desktop.panels.diff_card import (
    DiffApprovalCard,
    FileChangedNotification,
)
from src.gameforge_ide.desktop.panels.plan_card import PlanCard, STEP_STATUS_ICONS
from src.gameforge_ide.desktop.shell.rail import (
    RAIL_ITEMS,
    RETIRED_RAIL_ITEMS,
    Rail,
)
from src.gameforge_ide.desktop.shell.top_bar import TopBar


# ==============================================================================
# 1. TopBar: Task Mode and Autonomy Profile Selectors
# ==============================================================================

def test_top_bar_selectors_structure_and_options(qapp: QApplication):
    """Verify TopBar exposes task approach and autonomy profile combos with exact options."""
    top_bar = TopBar()
    try:
        # 1. Task Mode Combo
        assert hasattr(top_bar, "task_mode_combo")
        mode_combo: QComboBox = top_bar.task_mode_combo
        assert mode_combo.objectName() == "task_mode_combo"
        assert mode_combo.count() == 2
        mode_items = [mode_combo.itemText(i) for i in range(mode_combo.count())]
        assert "Planning" in mode_items
        assert "Fast" in mode_items
        assert mode_combo.currentText() == "Planning"

        # 2. Autonomy Profile Combo
        assert hasattr(top_bar, "autonomy_combo")
        autonomy_combo: QComboBox = top_bar.autonomy_combo
        assert autonomy_combo.objectName() == "autonomy_combo"
        assert autonomy_combo.count() == 3
        autonomy_items = [autonomy_combo.itemText(i) for i in range(autonomy_combo.count())]
        assert "Manual" in autonomy_items
        assert "Auto-Edit" in autonomy_items
        assert "Agentic" in autonomy_items
        assert autonomy_combo.currentText() == "Agentic"
    finally:
        top_bar.deleteLater()


def test_top_bar_signals_and_setters(qapp: QApplication):
    """Verify TopBar signals fire on selection and setters update without feedback loops."""
    top_bar = TopBar()
    try:
        emitted_modes: List[str] = []
        emitted_autonomies: List[str] = []
        top_bar.taskModeChanged.connect(emitted_modes.append)
        top_bar.autonomyProfileChanged.connect(emitted_autonomies.append)

        # User changes mode to Fast
        top_bar.task_mode_combo.setCurrentText("Fast")
        assert emitted_modes == ["Fast"]

        # User changes autonomy to Manual
        top_bar.autonomy_combo.setCurrentText("Manual")
        assert emitted_autonomies == ["Manual"]

        # Programmatic setters (block signals to avoid cyclic loops)
        top_bar.set_task_mode("planning")
        assert top_bar.task_mode_combo.currentText() == "Planning"
        assert emitted_modes == ["Fast"]  # No additional signal emitted

        top_bar.set_autonomy_profile("auto_edit")
        assert top_bar.autonomy_combo.currentText() == "Auto-Edit"
        assert emitted_autonomies == ["Manual"]  # No additional signal emitted
    finally:
        top_bar.deleteLater()


# ==============================================================================
# 2. ChatPanel: Task Mode and Autonomy Selectors
# ==============================================================================

def test_chat_panel_selectors_and_session_mode_sync(qapp: QApplication, temp_workspace: Path):
    """Verify ChatPanel exposes selectors and synchronizes changes to SessionManager."""
    sm = SessionManager(workspace_path=temp_workspace)
    session = sm.create_session(
        name="Chat Selector Session",
        task_mode=TaskMode.PLANNING,
        autonomy_profile=AutonomyProfile.AGENTIC,
    )

    chat = ChatPanel(workspace_root=temp_workspace)
    try:
        chat._session_id = session.session_id

        # Verify selectors exist on chat panel toolbar
        assert hasattr(chat, "task_mode_combo")
        assert hasattr(chat, "autonomy_combo")

        assert chat.task_mode_combo.currentText() == "Planning"
        assert chat.autonomy_combo.currentText() == "Agentic"

        # Track signals
        emitted_modes: List[str] = []
        emitted_autonomies: List[str] = []
        chat.task_mode_changed.connect(emitted_modes.append)
        chat.autonomy_changed.connect(emitted_autonomies.append)

        # 1. Switch to Fast mode
        chat.task_mode_combo.setCurrentText("Fast")
        assert emitted_modes == ["fast"]
        reloaded_sess = sm.get_session(session.session_id)
        assert reloaded_sess.task_mode == TaskMode.FAST

        # 2. Switch to Auto-Edit autonomy
        chat.autonomy_combo.setCurrentText("Auto-Edit")
        assert emitted_autonomies == ["auto_edit"]
        reloaded_sess_2 = sm.get_session(session.session_id)
        assert reloaded_sess_2.autonomy_profile == AutonomyProfile.AUTO_EDIT

        # 3. Test programmatic setters on ChatPanel
        chat.set_task_mode("planning")
        assert chat.task_mode_combo.currentText() == "Planning"

        chat.set_autonomy_profile("manual")
        assert chat.autonomy_combo.currentText() == "Manual"
    finally:
        chat.deleteLater()


# ==============================================================================
# 3. PlanCard: Interactive Plan Artifact Card Rendering
# ==============================================================================

def test_plan_card_rendering_and_proceed_button(
    qapp: QApplication,
    sample_plan_artifact: PlanArtifact,
):
    """Verify PlanCard renders goal, status, method, step checklist, and active Proceed button."""
    plan_dict = sample_plan_artifact.model_dump()
    card = PlanCard(plan_dict)
    try:
        # 1. Header info
        assert card.plan_id == sample_plan_artifact.plan_id
        assert card.version == 1
        assert "Implement Top-Down Roguelike Dash System" in card._lbl_title.text()
        assert "v1" in card._lbl_version.text()
        assert "AWAITING APPROVAL" in card._lbl_status.text()
        assert "Direct Code Edit" in card._lbl_method.text()

        # 2. Step widgets
        assert len(card._step_widgets) == 3
        assert "step_inspect_01" in card._step_widgets
        assert "step_implement_02" in card._step_widgets
        assert "step_verify_03" in card._step_widgets

        # 3. Proceed QPushButton exists and is enabled
        assert hasattr(card, "btn_proceed")
        assert card.btn_proceed.isEnabled() is True
        assert "Proceed" in card.btn_proceed.text()

        # 4. Revision input and button exist
        assert hasattr(card, "txt_revision")
        assert hasattr(card, "btn_revise")
        assert card.btn_revise.isEnabled() is True

        # 5. Clicking Proceed button emits proceed_clicked signal with plan_id
        emitted_proceed: List[str] = []
        card.proceed_clicked.connect(emitted_proceed.append)
        card.btn_proceed.click()

        assert emitted_proceed == [sample_plan_artifact.plan_id]
        # Proceed button locks after click
        assert card.btn_proceed.isEnabled() is False
        assert "Executing" in card.btn_proceed.text()
    finally:
        card.deleteLater()


def test_plan_card_inline_revision_dispatch(
    qapp: QApplication,
    sample_plan_artifact: PlanArtifact,
):
    """Verify typing into txt_revision and clicking btn_revise emits revision_requested."""
    plan_dict = sample_plan_artifact.model_dump()
    card = PlanCard(plan_dict)
    try:
        emitted_revisions: List[tuple] = []
        card.revision_requested.connect(lambda pid, rev: emitted_revisions.append((pid, rev)))

        card.txt_revision.setText("Add stamina consumption (25 per dash)")
        card.btn_revise.click()

        assert len(emitted_revisions) == 1
        pid, rev_text = emitted_revisions[0]
        assert pid == sample_plan_artifact.plan_id
        assert rev_text == "Add stamina consumption (25 per dash)"
        # Input is cleared after emission
        assert card.txt_revision.text() == ""
    finally:
        card.deleteLater()


def test_plan_card_step_status_updates(
    qapp: QApplication,
    sample_plan_artifact: PlanArtifact,
):
    """Verify update_step() updates live progress markers and step styling."""
    plan_dict = sample_plan_artifact.model_dump()
    card = PlanCard(plan_dict)
    try:
        step_id = "step_implement_02"

        # Update step to in_progress
        card.update_step(step_id, status="in_progress")
        step_frame = card._step_widgets[step_id]
        lbl_status = step_frame.findChild(QLabel, f"stepStatus_{step_id}")
        assert lbl_status is not None
        assert lbl_status.text() == "●"  # in_progress icon

        # Update step to completed
        card.update_step(step_id, status="completed", output_summary="Dash Impulse applied")
        assert lbl_status.text() == "✓"  # completed icon

        # Update step to failed
        card.update_step("step_verify_03", status="failed", error="AssertionError: Timeout")
        lbl_fail = card._step_widgets["step_verify_03"].findChild(QLabel, "stepStatus_step_verify_03")
        assert lbl_fail is not None
        assert lbl_fail.text() == "✗"  # failed icon
    finally:
        card.deleteLater()


def test_chat_panel_plan_event_creates_plan_card(
    qapp: QApplication,
    temp_workspace: Path,
    sample_plan_artifact: PlanArtifact,
):
    """Verify that ChatPanel._on_plan_received instantiates and registers a real PlanCard."""
    chat = ChatPanel(workspace_root=temp_workspace)
    try:
        plan_dict = sample_plan_artifact.model_dump()
        chat._on_plan_received(plan_dict)

        plan_id = sample_plan_artifact.plan_id
        assert plan_id in chat._plan_cards
        card = chat._plan_cards[plan_id]
        assert isinstance(card, PlanCard)
        assert card.goal == sample_plan_artifact.goal
        assert card.btn_proceed.isEnabled() is True
    finally:
        chat.deleteLater()


# ==============================================================================
# 4. DiffApprovalCard & FileChangedNotification
# ==============================================================================

def test_diff_approval_card_in_manual_profile(qapp: QApplication):
    """Verify DiffApprovalCard provides interactive Accept and Reject controls."""
    meta = {
        "file_path": "Source/Game/PlayerController.cpp",
        "diff_patch": "--- a/Player.cpp\n+++ b/Player.cpp\n@@ -10,3 +10,4 @@\n+void Dash();\n",
    }
    card = DiffApprovalCard("diff_9988", meta)
    try:
        assert hasattr(card, "btn_accept")
        assert hasattr(card, "btn_reject")
        assert card.btn_accept.isEnabled() is True
        assert card.btn_reject.isEnabled() is True

        # Test approve signal
        approved_diffs: List[str] = []
        card.diff_approved.connect(approved_diffs.append)
        card.btn_accept.click()

        assert approved_diffs == ["diff_9988"]
        assert card.btn_accept.isEnabled() is False
        assert card.btn_reject.isEnabled() is False
        assert "Accepted" in card.btn_accept.text()
    finally:
        card.deleteLater()


def test_diff_approval_card_rejection(qapp: QApplication):
    """Verify clicking Reject on DiffApprovalCard emits diff_rejected."""
    meta = {"file_path": "Config/DefaultEngine.ini", "diff_patch": ""}
    card = DiffApprovalCard("diff_reject_01", meta)
    try:
        rejected_diffs: List[str] = []
        card.diff_rejected.connect(rejected_diffs.append)
        card.btn_reject.click()

        assert rejected_diffs == ["diff_reject_01"]
        assert card.btn_accept.isEnabled() is False
        assert card.btn_reject.isEnabled() is False
        assert "Rejected" in card.btn_reject.text()
    finally:
        card.deleteLater()


def test_file_changed_notification_auto_edit_profile(qapp: QApplication):
    """Verify FileChangedNotification renders sleek non-blocking notification."""
    meta = {
        "file_path": "Source/Game/HeroCharacter.cpp",
        "diff_id": "diff_auto_001",
        "engineering_stage": "Code Generation",
    }
    notif = FileChangedNotification("Modified HeroCharacter.cpp with new bindings", meta)
    try:
        assert notif.objectName() == "fileChangedNotification"
        assert notif.accessibleName() == "File modification notification"
        # Does not have modal blocking buttons
        assert notif.findChild(QPushButton, "btnApproveDiff") is None
    finally:
        notif.deleteLater()


# ==============================================================================
# 5. Activity Rail: Retirement of Separate Design & Build Buttons
# ==============================================================================

def test_rail_primary_navigation_excludes_design_and_build(qapp: QApplication):
    """Verify that separate Design and Build views are absent from primary activity rail."""
    rail = Rail()
    try:
        # Primary RAIL_ITEMS must contain Home, Games, Play, Assets, Code, Settings
        rail_item_ids = [item[0] for item in RAIL_ITEMS]
        assert "home" in rail_item_ids
        assert "games" in rail_item_ids
        assert "play" in rail_item_ids
        assert "assets" in rail_item_ids
        assert "code" in rail_item_ids
        assert "settings" in rail_item_ids

        # Design and Build must NOT be in primary RAIL_ITEMS
        assert "design" not in rail_item_ids, "Design view must be retired from primary navigation rail"
        assert "build" not in rail_item_ids, "Build view must be retired from primary navigation rail"

        # Verify buttons dictionary in Rail instance
        assert rail.button("home") is not None
        assert rail.button("games") is not None
        assert rail.button("design") is None, "rail.button('design') must return None"
        assert rail.button("build") is None, "rail.button('build') must return None"

        # Verify RETIRED_RAIL_ITEMS records their retirement
        retired_ids = [item[0] for item in RETIRED_RAIL_ITEMS]
        assert "design" in retired_ids
        assert "build" in retired_ids
    finally:
        rail.deleteLater()


# ==============================================================================
# 6. Bidirectional Signal Wiring: TopBar <-> ChatPanel
# ==============================================================================

def test_bidirectional_mode_sync_top_bar_and_chat_panel(qapp: QApplication, temp_workspace: Path):
    """Verify mode and autonomy signals synchronize cleanly between TopBar and ChatPanel."""
    top_bar = TopBar()
    chat_panel = ChatPanel(workspace_root=temp_workspace)

    try:
        # Wire signals as done in MainWindow
        top_bar.taskModeChanged.connect(chat_panel.set_task_mode)
        top_bar.autonomyProfileChanged.connect(chat_panel.set_autonomy_profile)
        chat_panel.task_mode_changed.connect(top_bar.set_task_mode)
        chat_panel.autonomy_changed.connect(top_bar.set_autonomy_profile)

        # 1. Changing TopBar mode -> synchronizes ChatPanel
        top_bar.task_mode_combo.setCurrentText("Fast")
        assert chat_panel.task_mode_combo.currentText() == "Fast"

        # 2. Changing ChatPanel mode -> synchronizes TopBar
        chat_panel.task_mode_combo.setCurrentText("Planning")
        assert top_bar.task_mode_combo.currentText() == "Planning"

        # 3. Changing TopBar autonomy -> synchronizes ChatPanel
        top_bar.autonomy_combo.setCurrentText("Manual")
        assert chat_panel.autonomy_combo.currentText() == "Manual"

        # 4. Changing ChatPanel autonomy -> synchronizes TopBar
        chat_panel.autonomy_combo.setCurrentText("Auto-Edit")
        assert top_bar.autonomy_combo.currentText() == "Auto-Edit"
    finally:
        top_bar.deleteLater()
        chat_panel.deleteLater()
