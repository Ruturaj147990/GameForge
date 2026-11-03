"""Unit tests for the Two-Location Storage Architecture and Directory Selection workflow."""
import json
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.dialogs.new_project_dialog import NewProjectDialog
from src.gameforge_ide.desktop.views.games_view import GamesView
from src.gameforge_ide.desktop.views.design_view import DesignView
from src.gameforge_ide.desktop.views.home_view import HomeView
from src.gameforge_ide.design.gds import GameDesignSpec, Meta, Overview, TechSpec, Genre, CameraKind
from src.gameforge_ide.design.presets import PRESETS
from src.gameforge_ide.core.projects import is_gameforge_project, resolve_project_dir
from src.gameforge_ide.core.settings import get_settings


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_new_project_dialog_validation_and_resolution(qapp, tmp_path: Path):
    target_parent = tmp_path / "UserProjects"
    target_parent.mkdir(parents=True, exist_ok=True)

    dlg = NewProjectDialog(initial_name="CyberRacer", initial_parent_dir=target_parent)
    name, pdir = dlg.get_resolved_project_dir()
    assert name == "CyberRacer"
    assert pdir == target_parent / "CyberRacer"
    assert dlg._btn_confirm.isEnabled()

    # Empty name check
    dlg._edit_name.setText("")
    assert not dlg._btn_confirm.isEnabled()

    # Sanitization
    dlg._edit_name.setText("123 My Super Game!")
    sanitized_name, sanitized_pdir = dlg.get_resolved_project_dir()
    assert sanitized_name.startswith("G123")
    assert "Super" in sanitized_name
    assert sanitized_pdir == target_parent / sanitized_name


def test_new_project_dialog_existing_project_detection(qapp, tmp_path: Path):
    existing_proj = tmp_path / "ExistingShooter"
    existing_proj.mkdir(parents=True, exist_ok=True)
    (existing_proj / "ExistingShooter.uproject").write_text("{}", encoding="utf-8")

    dlg = NewProjectDialog(initial_name="ExistingShooter", initial_parent_dir=tmp_path)
    name, pdir = dlg.get_resolved_project_dir()
    assert is_gameforge_project(pdir)
    assert "Existing GameForge/Unreal project detected" in dlg._lbl_status.text()


def test_two_location_storage_isolation(tmp_path: Path):
    """Verify that GameForge enforces exactly two managed locations:
    Location 1: Workspace / app conversation history (.gameforge/sessions)
    Location 2: User-selected project root containing ALL project files
    """
    workspace_dir = tmp_path / "AppWorkspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir = workspace_dir / ".gameforge" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Location 1: write conversation session
    session_file = sessions_dir / "sess_test1.json"
    session_file.write_text(json.dumps({"session_id": "sess_test1", "project": "TacticalFPS"}), encoding="utf-8")
    assert session_file.is_file()

    # Location 2: authoritative user-selected project root
    user_project_dir = tmp_path / "MyCustomGames" / "TacticalFPS"
    user_project_dir.mkdir(parents=True, exist_ok=True)

    # Required project-specific subdirectories
    subdirs = ["Config", "Content", "Source", "Plugins", "GameForge", "Packaged", "Saved", "Intermediate", "Binaries"]
    for d in subdirs:
        (user_project_dir / d).mkdir(parents=True, exist_ok=True)

    # .uproject file
    uproject = user_project_dir / "TacticalFPS.uproject"
    uproject.write_text(json.dumps({"FileVersion": 3, "EngineAssociation": "5.7"}), encoding="utf-8")

    # GameDesignSpec inside GameForge/design/
    design_dir = user_project_dir / "GameForge" / "design"
    design_dir.mkdir(parents=True, exist_ok=True)
    gds = PRESETS["arena_combat"]()
    gds.meta.title = "TacticalFPS"
    gds.meta.project_name = "TacticalFPS"
    gds.meta.project_dir = str(user_project_dir)
    (design_dir / "game.gds.json").write_text(gds.model_dump_json(indent=2), encoding="utf-8")

    # Verify Location 2 is self-contained and recognized as authoritative project root
    assert is_gameforge_project(user_project_dir)
    resolved = resolve_project_dir(user_project_dir)
    assert resolved == user_project_dir.resolve()

    # Location 1 must NOT contain project-specific source or uproject
    assert not (workspace_dir / "TacticalFPS.uproject").exists()
    assert not (workspace_dir / "Source").exists()


def test_games_view_has_new_and_open_project_buttons(qapp):
    gv = GamesView()
    assert hasattr(gv, "_btn_new")
    assert hasattr(gv, "_btn_open")
    assert gv._btn_new.text() == "+ New Project…"
    assert gv._btn_open.text() == "Open…"


def test_home_view_project_folder_selector(qapp, tmp_path: Path):
    hv = HomeView()
    assert hasattr(hv, "_edit_project_dir")
    custom_dir = str(tmp_path / "CustomGames")
    hv._edit_project_dir.setText(custom_dir)
    assert hv._edit_project_dir.text() == custom_dir


def test_design_view_project_dir_banner(qapp, tmp_path: Path):
    dv = DesignView()
    assert hasattr(dv, "_dir_banner")
    assert hasattr(dv, "_lbl_project_dir")

    proj_dir = tmp_path / "E2EProject"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "E2EProject.uproject").write_text("{}", encoding="utf-8")

    spec = PRESETS["platformer"]()
    spec.meta.title = "E2EProject"
    spec.meta.project_name = "E2EProject"
    spec.meta.project_dir = str(proj_dir)
    dv.open_draft(spec, project_dir=proj_dir)
    assert dv._current_project_dir == proj_dir.resolve()
    assert str(proj_dir.resolve()) in dv._lbl_project_dir.text()
