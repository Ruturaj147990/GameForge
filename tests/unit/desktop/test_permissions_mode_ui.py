"""Comprehensive PySide6 UI Unit Tests for Permissions Mode (DEF-306).

Validates:
1. TopBar Permissions Mode dropdown:
   - Contains exactly: "Request All", "Auto", "Unrestricted"
   - Default is "Auto"
   - Keeps Approach Mode ("Planning", "Fast") completely independent
   - Emits permissionsModeChanged signal with canonical mode ("request_all", "auto", "unrestricted")
   - Programmatic setter set_permissions_mode() updates without feedback loops
   - Backward compatibility aliases: autonomy_combo, autonomyProfileChanged, set_autonomy_profile()
2. ChatPanel Permissions Mode dropdown:
   - Header toolbar titled "Permissions Mode:" with items "Request All", "Auto", "Unrestricted"
   - Emits permissions_mode_changed signal
   - Updates session mode in SessionManager
   - Persists user selection to QSettings
   - Restores persisted selection on launch and new session
3. Bidirectional Synchronization:
   - TopBar -> ChatPanel synchronization
   - ChatPanel -> TopBar synchronization
4. SettingsView integration:
   - Exposes Default Permissions Mode and Default Approach Mode controls
   - Saves and reloads settings cleanly
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QLabel

from src.gameforge_ide.backend.models.modes import AutonomyProfile, PermissionsMode, TaskMode
from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel
from src.gameforge_ide.desktop.shell.top_bar import TopBar
from src.gameforge_ide.desktop.views.settings_view import SettingsView


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "test_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ==============================================================================
# 1. TopBar Permissions Mode Selectors
# ==============================================================================

def test_top_bar_permissions_mode_structure_and_independence(qapp: QApplication):
    """Verify TopBar exposes Permissions Mode with exact items and keeps Approach independent."""
    top_bar = TopBar()
    try:
        # 1. Approach mode must be present and completely independent
        assert hasattr(top_bar, "task_mode_combo")
        approach_items = [top_bar.task_mode_combo.itemText(i) for i in range(top_bar.task_mode_combo.count())]
        assert approach_items == ["Planning", "Fast"]

        # 2. Permissions mode combo
        assert hasattr(top_bar, "permissions_mode_combo")
        perm_combo: QComboBox = top_bar.permissions_mode_combo
        assert perm_combo.objectName() == "permissions_mode_combo"
        assert perm_combo.count() == 3

        items = [perm_combo.itemText(i) for i in range(perm_combo.count())]
        assert items == ["Request All", "Auto", "Unrestricted"]
        assert perm_combo.currentText() == "Auto"

        # Check aliases
        assert top_bar.permissions_combo is perm_combo
        assert top_bar.permissionsModeCombo is perm_combo
        assert hasattr(top_bar, "lbl_permissions_mode")
        assert "Permissions Mode" in top_bar.lbl_permissions_mode.text()
    finally:
        top_bar.deleteLater()


def test_top_bar_permissions_mode_signals_and_setters(qapp: QApplication):
    """Verify TopBar signals emit canonical values and setters update cleanly."""
    top_bar = TopBar()
    try:
        emitted_perms: List[str] = []
        emitted_autonomies: List[str] = []
        top_bar.permissionsModeChanged.connect(emitted_perms.append)
        top_bar.autonomyProfileChanged.connect(emitted_autonomies.append)

        # 1. Switch to Request All
        top_bar.permissions_mode_combo.setCurrentText("Request All")
        assert emitted_perms == ["request_all"]
        assert "Manual" in emitted_autonomies

        # 2. Switch to Unrestricted
        top_bar.permissions_mode_combo.setCurrentText("Unrestricted")
        assert emitted_perms == ["request_all", "unrestricted"]
        assert "Agentic" in emitted_autonomies

        # 3. Switch back to Auto
        top_bar.permissions_mode_combo.setCurrentText("Auto")
        assert emitted_perms == ["request_all", "unrestricted", "auto"]

        # 4. Programmatic setter (must block feedback loops)
        signal_count_before = len(emitted_perms)
        top_bar.set_permissions_mode("request_all")
        assert top_bar.permissions_mode_combo.currentText() == "Request All"
        assert len(emitted_perms) == signal_count_before  # No new signal

        top_bar.set_permissions_mode("unrestricted")
        assert top_bar.permissions_mode_combo.currentText() == "Unrestricted"
        assert len(emitted_perms) == signal_count_before

        top_bar.set_permissions_mode("auto")
        assert top_bar.permissions_mode_combo.currentText() == "Auto"
        assert len(emitted_perms) == signal_count_before
    finally:
        top_bar.deleteLater()


def test_top_bar_autonomy_backward_compatibility(qapp: QApplication):
    """Verify legacy AutonomyProfile methods and properties map seamlessly."""
    top_bar = TopBar()
    try:
        assert hasattr(top_bar, "autonomy_combo")
        assert top_bar.autonomy_combo.count() == 3
        legacy_items = [top_bar.autonomy_combo.itemText(i) for i in range(top_bar.autonomy_combo.count())]
        assert legacy_items == ["Manual", "Auto-Edit", "Agentic"]

        # Setting legacy profile updates permissions combo
        top_bar.set_autonomy_profile("manual")
        assert top_bar.permissions_mode_combo.currentText() == "Request All"

        top_bar.set_autonomy_profile("auto_edit")
        assert top_bar.permissions_mode_combo.currentText() == "Auto"

        top_bar.set_autonomy_profile("agentic")
        assert top_bar.permissions_mode_combo.currentText() in ("Auto", "Unrestricted")
    finally:
        top_bar.deleteLater()


# ==============================================================================
# 2. ChatPanel Permissions Mode Selectors & Persistence
# ==============================================================================

def test_chat_panel_permissions_mode_structure_and_tooltip(qapp: QApplication, temp_workspace: Path):
    """Verify ChatPanel has Permissions Mode dropdown on toolbar with rich tooltip."""
    chat = ChatPanel(workspace_root=temp_workspace)
    try:
        assert hasattr(chat, "permissions_mode_combo")
        perm_combo: QComboBox = chat.permissions_mode_combo
        assert perm_combo.objectName() == "permissions_mode_combo"
        assert perm_combo.count() == 3

        items = [perm_combo.itemText(i) for i in range(perm_combo.count())]
        assert items == ["Request All", "Auto", "Unrestricted"]

        # Tooltip should explain all 3 modes
        tip = perm_combo.toolTip()
        assert "Request All" in tip
        assert "Auto" in tip
        assert "Unrestricted" in tip

        # Label title
        assert hasattr(chat, "lbl_permissions_mode")
        assert "Permissions Mode" in chat.lbl_permissions_mode.text()

        # Approach combo is independent
        assert hasattr(chat, "task_mode_combo")
        assert [chat.task_mode_combo.itemText(i) for i in range(2)] == ["Planning", "Fast"]
    finally:
        chat.deleteLater()


def test_chat_panel_permissions_mode_signal_and_session_sync(qapp: QApplication, temp_workspace: Path):
    """Verify ChatPanel emits permissions_mode_changed and updates session mode."""
    sm = SessionManager(workspace_path=temp_workspace)
    session = sm.create_session(
        name="Perms Session",
        task_mode=TaskMode.PLANNING,
        autonomy_profile=AutonomyProfile.AGENTIC,
    )

    chat = ChatPanel(workspace_root=temp_workspace)
    try:
        chat._session_id = session.session_id

        emitted_perms: List[str] = []
        chat.permissions_mode_changed.connect(emitted_perms.append)

        # 1. Switch to Request All
        chat.permissions_mode_combo.setCurrentText("Request All")
        assert emitted_perms == ["request_all"]

        # Check session manager updated
        reloaded = sm.get_session(session.session_id)
        assert reloaded.autonomy_profile == AutonomyProfile.MANUAL

        # 2. Switch to Unrestricted
        chat.permissions_mode_combo.setCurrentText("Unrestricted")
        assert emitted_perms == ["request_all", "unrestricted"]

        # Check session manager updated
        reloaded = sm.get_session(session.session_id)
        assert reloaded.autonomy_profile == AutonomyProfile.AGENTIC

        # 3. Switch to Auto
        chat.permissions_mode_combo.setCurrentText("Auto")
        assert emitted_perms == ["request_all", "unrestricted", "auto"]
        reloaded = sm.get_session(session.session_id)
        assert reloaded.autonomy_profile == AutonomyProfile.AUTO_EDIT
    finally:
        chat.deleteLater()


def test_chat_panel_permissions_mode_persistence(qapp: QApplication, temp_workspace: Path):
    """Verify Permissions Mode selection persists in workspace ide_settings.ini and restores."""
    # Write initial setting to Request All in workspace
    ini_path = temp_workspace / ".gameforge" / "ide_settings.ini"
    ini_path.parent.mkdir(parents=True, exist_ok=True)
    qs = QSettings(str(ini_path), QSettings.IniFormat)
    qs.setValue("preferences/permissions_mode", "request_all")
    qs.sync()

    # Launch ChatPanel with this workspace
    chat = ChatPanel(workspace_root=temp_workspace)
    try:
        # Must restore Request All
        assert chat.permissions_mode_combo.currentText() == "Request All"

        # Change to Unrestricted
        chat.permissions_mode_combo.setCurrentText("Unrestricted")

        # Verify persisted
        qs2 = QSettings(str(ini_path), QSettings.IniFormat)
        assert qs2.value("preferences/permissions_mode") == "unrestricted"

        # Create new session - must maintain Unrestricted
        chat._new_session()
        assert chat.permissions_mode_combo.currentText() == "Unrestricted"
    finally:
        chat.deleteLater()


# ==============================================================================
# 3. Bidirectional Synchronization between TopBar and ChatPanel
# ==============================================================================

def test_bidirectional_permissions_mode_synchronization(qapp: QApplication, temp_workspace: Path):
    """Verify TopBar and ChatPanel remain in sync when connected."""
    top_bar = TopBar()
    chat = ChatPanel(workspace_root=temp_workspace)
    try:
        # Wire signals as MainWindow does
        top_bar.permissionsModeChanged.connect(chat.set_permissions_mode)
        chat.permissions_mode_changed.connect(top_bar.set_permissions_mode)

        # 1. Change in TopBar -> ChatPanel reflects it
        top_bar.permissions_mode_combo.setCurrentText("Request All")
        assert chat.permissions_mode_combo.currentText() == "Request All"

        top_bar.permissions_mode_combo.setCurrentText("Unrestricted")
        assert chat.permissions_mode_combo.currentText() == "Unrestricted"

        # 2. Change in ChatPanel -> TopBar reflects it
        chat.permissions_mode_combo.setCurrentText("Auto")
        assert top_bar.permissions_mode_combo.currentText() == "Auto"

        chat.permissions_mode_combo.setCurrentText("Request All")
        assert top_bar.permissions_mode_combo.currentText() == "Request All"
    finally:
        top_bar.deleteLater()
        chat.deleteLater()


# ==============================================================================
# 4. SettingsView Permissions Mode Controls
# ==============================================================================

def test_settings_view_permissions_mode_controls(qapp: QApplication, temp_workspace: Path, monkeypatch):
    """Verify SettingsView exposes and saves Default Permissions Mode and Default Approach Mode."""
    cfg_file = temp_workspace / "settings.json"
    monkeypatch.setenv("GAMEFORGE_USER_SETTINGS", str(cfg_file))

    view = SettingsView(workspace_root=temp_workspace)
    try:
        assert hasattr(view, "_permissions_mode_combo")
        assert hasattr(view, "_task_mode_combo")

        perm_items = [view._permissions_mode_combo.itemText(i) for i in range(view._permissions_mode_combo.count())]
        assert perm_items == ["Request All", "Auto", "Unrestricted"]

        task_items = [view._task_mode_combo.itemText(i) for i in range(view._task_mode_combo.count())]
        assert task_items == ["Planning", "Fast"]

        # Modify values and save
        view._permissions_mode_combo.setCurrentText("Request All")
        view._task_mode_combo.setCurrentText("Fast")
        view.save_settings()

        # Check saved in workspace ide_settings.ini
        ini_path = temp_workspace / ".gameforge" / "ide_settings.ini"
        assert ini_path.is_file()
        qs = QSettings(str(ini_path), QSettings.IniFormat)
        assert qs.value("preferences/permissions_mode") == "request_all"
        assert qs.value("preferences/task_mode") == "fast"
    finally:
        view.deleteLater()
