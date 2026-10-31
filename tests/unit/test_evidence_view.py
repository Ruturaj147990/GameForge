"""Unit tests for Studio UX Evidence view (spec §4.6, WI-4.9)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.desktop.views.evidence_view import EvidenceView


@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_evidence_view_widget_hierarchy(qapp):
    """Verify EvidenceView creates required objectNames and accessible names."""
    view = EvidenceView()
    try:
        assert view.objectName() == "evidenceView"
        assert view.accessibleName() == "GameForge Evidence View"

        assert view.findChild(object, "lblEvidenceTitle") is not None
        assert view.findChild(object, "btnEvidenceRefresh") is not None
        assert view.findChild(object, "evidenceFilterCombo") is not None
        assert view.findChild(object, "lblEvidenceSummary") is not None
        assert view.findChild(object, "evidenceGallery") is not None
        assert view.findChild(object, "evidenceViewerStack") is not None
        assert view.findChild(object, "evidenceImageLabel") is not None
        assert view.findChild(object, "evidenceTextViewer") is not None
        assert view.findChild(object, "evidenceMarkdownViewer") is not None
    finally:
        view.deleteLater()


def test_evidence_view_populates_gallery_and_filters(qapp, tmp_path):
    """Verify EvidenceView populates gallery from files and filters correctly."""
    proj_dir = tmp_path / "MyProject"
    ev_dir = proj_dir / "Saved" / "GameForge" / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy artifact files
    (ev_dir / "screenshot1.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")
    (ev_dir / "summary.json").write_text(json.dumps({"test": "ok"}), encoding="utf-8")
    (ev_dir / "notes.md").write_text("# Notes\n\nSome findings.", encoding="utf-8")
    (ev_dir / "build.log").write_text("[UBT] Compiled OK", encoding="utf-8")

    view = EvidenceView(workspace_root=tmp_path)
    try:
        view._artifact_paths = [
            ev_dir / "screenshot1.png",
            ev_dir / "summary.json",
            ev_dir / "notes.md",
            ev_dir / "build.log",
        ]
        view._populate_gallery()

        assert view._gallery.count() == 4

        # Test filtering
        view._filter_combo.setCurrentText("Images")
        assert view._gallery.count() == 1

        view._filter_combo.setCurrentText("JSON")
        assert view._gallery.count() == 1

        view._filter_combo.setCurrentText("Logs")
        assert view._gallery.count() == 1

        view._filter_combo.setCurrentText("All")
        assert view._gallery.count() == 4
    finally:
        view.deleteLater()


def test_evidence_view_preview_types(qapp, tmp_path):
    """Verify EvidenceView displays JSON, Markdown, and text in detail pane."""
    view = EvidenceView(workspace_root=tmp_path)
    try:
        json_file = tmp_path / "data.json"
        json_file.write_text(json.dumps({"key": "value"}), encoding="utf-8")

        view._show_json(json_file)
        assert view._viewer_stack.currentIndex() == 1
        assert '"key": "value"' in view._text_viewer.toPlainText()

        md_file = tmp_path / "report.md"
        md_file.write_text("# Heading\n\nParagraph", encoding="utf-8")

        view._show_markdown(md_file)
        assert view._viewer_stack.currentIndex() == 2
        assert "Heading" in view._md_viewer.toPlainText()
    finally:
        view.deleteLater()


def test_evidence_view_no_raw_hex_colors():
    """Verify zero raw hex colors in evidence view source."""
    pattern = re.compile(r'#[0-9a-fA-F]{3,8}\b')
    f = Path("src/gameforge_ide/desktop/views/evidence_view.py")
    assert f.is_file(), f"Missing file {f}"
    text = f.read_text(encoding="utf-8")
    matches = pattern.findall(text)
    assert not matches, f"Raw hex color literals found in {f}: {matches}"
