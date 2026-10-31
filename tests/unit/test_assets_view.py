"""Unit tests for Studio UX Assets view (spec §4.7, WI-4.10)."""
from __future__ import annotations

import os
from pathlib import Path
import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.backend.assets.registry import AssetRecord, AssetRegistry
from src.gameforge_ide.desktop.views.assets_view import AssetsView


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_assets_view_widget_hierarchy(qapp, tmp_path):
    """Verify AssetsView creates required objectNames and accessible names."""
    view = AssetsView(workspace_root=tmp_path)
    try:
        assert view.objectName() == "assetsView"
        assert view.accessibleName() == "GameForge Assets View"

        assert view.findChild(object, "lblAssetsTitle") is not None
        assert view.findChild(object, "assetsSearchInput") is not None
        assert view.findChild(object, "assetsTypeCombo") is not None
        assert view.findChild(object, "assetsStageCombo") is not None
        assert view.findChild(object, "btnAssetsRefresh") is not None
        assert view.findChild(object, "lblAssetsSummary") is not None
        assert view.findChild(object, "assetsTableView") is not None
        assert view.findChild(object, "assetsDetailText") is not None
    finally:
        view.deleteLater()


def test_assets_view_search_and_filter(qapp, tmp_path):
    """Verify AssetsView reflects records from AssetRegistry."""
    reg = AssetRegistry(tmp_path)
    rec1 = AssetRecord(
        name="SM_HeroSword",
        asset_type="mesh",
        purpose="Player weapon",
        provenance="procedural",
        backend="geometry_script",
        backend_version="1.0",
        license="MIT",
        spec={"poly_count": 500},
        tags=["weapon", "melee"],
    )
    rec2 = AssetRecord(
        name="T_Cobblestone_D",
        asset_type="texture",
        purpose="Floor material",
        provenance="procedural",
        backend="texture_gen",
        backend_version="1.0",
        license="MIT",
        spec={"resolution": 1024},
        tags=["surface"],
    )
    id1 = reg.register(rec1)
    id2 = reg.register(rec2)
    reg.advance(id1, "ENGINE_VERIFY", ok=True, detail="Engine verified")
    reg.advance(id1, "PROMOTE", ok=True, detail="Ready for engine", evidence=["test.png"])

    view = AssetsView(workspace_root=tmp_path)
    try:
        view.refresh_assets()
        assert view._model.rowCount() == 2

        # Filter by type: mesh
        view._type_combo.setCurrentText("mesh")
        assert view._model.rowCount() == 1
        assert view._model.data(view._model.index(0, 0), Qt.DisplayRole) == "SM_HeroSword"

        # Clear type filter, filter by search text
        view._type_combo.setCurrentIndex(0)
        view._search_input.setText("Cobblestone")
        assert view._model.rowCount() == 1
        assert view._model.data(view._model.index(0, 0), Qt.DisplayRole) == "T_Cobblestone_D"
    finally:
        view.deleteLater()


def test_assets_view_no_raw_hex_colors():
    """Verify zero raw hex colors in assets view source."""
    pattern = re.compile(r'#[0-9a-fA-F]{3,8}\b')
    f = Path("src/gameforge_ide/desktop/views/assets_view.py")
    assert f.is_file(), f"Missing file {f}"
    text = f.read_text(encoding="utf-8")
    matches = pattern.findall(text)
    assert not matches, f"Raw hex color literals found in {f}: {matches}"
