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


def test_assets_view_sortable_columns_and_size_calculation(qapp, tmp_path):
    """Verify AssetsView displays Size column, calculates size, and sorts correctly."""
    view = AssetsView(workspace_root=tmp_path)
    try:
        # Create dummy artifact files
        art_small = tmp_path / "sword.fbx"
        art_small.write_bytes(b"x" * 512)  # 512 B

        art_large = tmp_path / "castle.fbx"
        art_large.write_bytes(b"x" * (2 * 1024 * 1024))  # 2.0 MB

        rows = [
            {
                "asset_id": "mesh:sword:123",
                "name": "SM_Sword",
                "asset_type": "mesh",
                "stage": "SPEC",
                "artifact_path": str(art_small),
                "license": "MIT",
                "provenance": "procedural",
                "backend": "csg",
            },
            {
                "asset_id": "mesh:castle:456",
                "name": "SM_Castle",
                "asset_type": "mesh",
                "stage": "PROMOTE",
                "artifact_path": str(art_large),
                "license": "CC0",
                "provenance": "imported",
                "backend": "fbx",
            },
        ]
        view._model.set_rows(rows)
        assert view._model.rowCount() == 2

        # Check Column 3 (Size)
        sz_0 = view._model.data(view._model.index(0, 3), Qt.DisplayRole)
        sz_1 = view._model.data(view._model.index(1, 3), Qt.DisplayRole)
        assert "512 B" in sz_0
        assert "2.0 MB" in sz_1

        # Sort descending by size (Col 3)
        view._model.sort(3, Qt.DescendingOrder)
        assert view._model.data(view._model.index(0, 0), Qt.DisplayRole) == "SM_Castle"
        assert view._model.data(view._model.index(1, 0), Qt.DisplayRole) == "SM_Sword"

        # Sort ascending by name (Col 0)
        view._model.sort(0, Qt.AscendingOrder)
        assert view._model.data(view._model.index(0, 0), Qt.DisplayRole) == "SM_Castle"
        assert view._model.data(view._model.index(1, 0), Qt.DisplayRole) == "SM_Sword"
    finally:
        view.deleteLater()


def test_assets_view_thumbnail_preview_and_detail(qapp, tmp_path):
    """Verify detail drawer updates thumbnail preview and properties on asset selection."""
    from PySide6.QtGui import QImage

    view = AssetsView(workspace_root=tmp_path)
    try:
        # Create dummy png image
        img_path = tmp_path / "test_thumb.png"
        img = QImage(64, 64, QImage.Format_RGB32)
        img.fill(0x7C3AED)
        img.save(str(img_path))

        rows = [
            {
                "asset_id": "tex:wood:789",
                "name": "T_Wood_D",
                "asset_type": "texture",
                "stage": "PROMOTE",
                "preview_path": str(img_path),
                "license": "CC0",
                "provenance": "procedural",
                "backend": "substance",
                "tags": "wood, surface",
                "purpose": "Floor plank texture",
            }
        ]
        view._model.set_rows(rows)
        view._table.setCurrentIndex(view._model.index(0, 0))
        view._on_asset_selected(view._model.index(0, 0))

        assert "T_Wood_D" in view._lbl_detail_header.text()
        assert not view._lbl_thumbnail.pixmap().isNull()
        detail_text = view._detail_text.toPlainText()
        assert "wood, surface" in detail_text
        assert "Floor plank texture" in detail_text
        assert "CC0" in detail_text
    finally:
        view.deleteLater()

