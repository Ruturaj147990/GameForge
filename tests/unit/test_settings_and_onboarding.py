"""Unit tests for Settings view and Onboarding wizard (spec §4.9–4.10, WI-4.10)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.core.settings import get_settings, reset_settings_cache
from src.gameforge_ide.desktop.views.onboarding import OnboardingWizard
from src.gameforge_ide.desktop.views.settings_view import SettingsView


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_settings_view_widget_hierarchy(qapp, tmp_path):
    """Verify SettingsView creates expected objectNames and accessible names."""
    view = SettingsView(workspace_root=tmp_path)
    try:
        assert view.objectName() == "settingsView"
        assert view.accessibleName() == "GameForge Settings View"

        assert view.findChild(object, "lblSettingsTitle") is not None
        assert view.findChild(object, "btnSettingsSave") is not None
        assert view.findChild(object, "groupSettingsEngine") is not None
        assert view.findChild(object, "settingsEnginePathInput") is not None
        assert view.findChild(object, "groupSettingsPaths") is not None
        assert view.findChild(object, "settingsProjectsRootInput") is not None
        assert view.findChild(object, "settingsArtifactsRootInput") is not None
        assert view.findChild(object, "settingsOllamaUrlInput") is not None
        assert view.findChild(object, "groupSettingsModels") is not None
        assert view.findChild(object, "settingsModelsTable") is not None
        assert view.findChild(object, "groupSettingsAppearance") is not None
    finally:
        view.deleteLater()


def test_settings_view_save_and_signal(qapp, tmp_path, monkeypatch):
    """Verify SettingsView saves configuration and emits settingsChanged."""
    cfg_file = tmp_path / "settings.json"
    monkeypatch.setenv("GAMEFORGE_USER_SETTINGS", str(cfg_file))
    reset_settings_cache()

    view = SettingsView(workspace_root=tmp_path)
    try:
        view._projects_root_input.setText(str(tmp_path / "MyProjects"))
        view._ollama_url_input.setText("http://127.0.0.1:11434")

        emitted = []
        view.settingsChanged.connect(lambda: emitted.append(True))
        view.save_settings()

        assert len(emitted) == 1
        assert cfg_file.is_file()
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert data.get("projects_root") == str(tmp_path / "MyProjects")
    finally:
        view.deleteLater()


def test_onboarding_wizard_pages(qapp, tmp_path, monkeypatch):
    """Verify OnboardingWizard contains 3 pages and writes settings on accept."""
    cfg_file = tmp_path / "onboard_settings.json"
    monkeypatch.setenv("GAMEFORGE_USER_SETTINGS", str(cfg_file))
    reset_settings_cache()

    wizard = OnboardingWizard()
    try:
        assert len(wizard.pageIds()) == 3
        assert wizard.engine_page.objectName() == "onboardingEnginePage"
        assert wizard.paths_page.objectName() == "onboardingPathsPage"
        assert wizard.models_page.objectName() == "onboardingModelsPage"

        wizard.paths_page._projects_path.setText(str(tmp_path / "OnboardProjects"))
        wizard.accept()

        assert cfg_file.is_file()
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert data.get("projects_root") == str(tmp_path / "OnboardProjects")
    finally:
        wizard.deleteLater()


def test_settings_and_onboarding_no_raw_hex():
    """Verify zero raw hex colors in settings view and onboarding source."""
    pattern = re.compile(r'#[0-9a-fA-F]{3,8}\b')
    for f in (
        Path("src/gameforge_ide/desktop/views/settings_view.py"),
        Path("src/gameforge_ide/desktop/views/onboarding.py"),
    ):
        text = f.read_text(encoding="utf-8")
        matches = pattern.findall(text)
        assert not matches, f"Raw hex color literals found in {f}: {matches}"
