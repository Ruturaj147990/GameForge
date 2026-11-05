"""Evidence view for Studio UX v2 (spec §4.6, WI-4.9).

Gallery of all run artifacts for the selected project with detail pane:
- Image viewer (fit/zoom)
- Markdown viewer
- JSON viewer
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QEvent, QModelIndex, QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.core.projects import resolve_project_dir, open_folder_in_file_manager
from src.gameforge_ide.forge.model import ArtifactRef, RunState
from src.gameforge_ide.forge.store import RunStore

logger = logging.getLogger(__name__)

# File extensions by viewer type
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
JSON_EXTS = {".json"}
MARKDOWN_EXTS = {".md", ".markdown"}
TEXT_EXTS = {".txt", ".log", ".csv", ".ini", ".cfg"}


class EvidenceView(QWidget):
    """Evidence gallery of all run artifacts for the current project."""

    openFileRequested = Signal(str)  # absolute path

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("evidenceView")
        self.setAccessibleName("GameForge Evidence View")

        self._workspace = Path(workspace_root or Path.cwd()).resolve()
        self._store = RunStore(project_dir=None, workspace_dir=self._workspace)
        self._current_project: Optional[str] = None
        self._artifact_paths: List[Path] = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(tokens.SPACE_MD)

        # ── Header ───────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(tokens.SPACE_MD)

        lbl_title = QLabel("Evidence", self)
        lbl_title.setObjectName("lblEvidenceTitle")
        lbl_title.setAccessibleName("Evidence gallery title")
        lbl_title.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_HEADING}px; font-weight: 700;"
        )
        header.addWidget(lbl_title)

        header.addStretch(1)

        # Filter combo
        self._filter_combo = QComboBox(self)
        self._filter_combo.setObjectName("evidenceFilterCombo")
        self._filter_combo.setAccessibleName("Filter artifacts by type")
        self._filter_combo.addItems(["All", "Images", "JSON", "Reports / Docs", "Logs", "Other"])
        self._filter_combo.setStyleSheet(
            f"QComboBox#{self._filter_combo.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
        )
        self._filter_combo.currentIndexChanged.connect(self._apply_filter)
        header.addWidget(self._filter_combo)

        self._btn_refresh = QPushButton("Refresh", self)
        self._btn_refresh.setObjectName("btnEvidenceRefresh")
        self._btn_refresh.setAccessibleName("Refresh evidence gallery")
        self._btn_refresh.setCursor(Qt.PointingHandCursor)
        self._btn_refresh.setStyleSheet(
            f"QPushButton#{self._btn_refresh.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self._btn_refresh.objectName()}:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        self._btn_refresh.clicked.connect(self.refresh_artifacts)
        header.addWidget(self._btn_refresh)

        main_layout.addLayout(header)

        # ── Summary ──────────────────────────────────────────────────────────
        self._lbl_summary = QLabel("No artifacts loaded.", self)
        self._lbl_summary.setObjectName("lblEvidenceSummary")
        self._lbl_summary.setAccessibleName("Evidence artifacts summary")
        self._lbl_summary.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;"
        )
        main_layout.addWidget(self._lbl_summary)

        # ── Splitter: Gallery List + Detail Pane ─────────────────────────────
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setObjectName("evidenceSplitter")

        # Left: gallery list
        self._gallery = QListWidget(splitter)
        self._gallery.setObjectName("evidenceGallery")
        self._gallery.setAccessibleName("Evidence artifacts gallery")
        self._gallery.setViewMode(QListWidget.IconMode)
        self._gallery.setIconSize(QSize(120, 90))
        self._gallery.setResizeMode(QListWidget.Adjust)
        self._gallery.setSpacing(8)
        self._gallery.setSelectionMode(QAbstractItemView.SingleSelection)
        self._gallery.setStyleSheet(
            f"QListWidget#{self._gallery.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"}}"
            f"QListWidget#{self._gallery.objectName()}::item {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: 4px;"
            f"  padding: 4px;"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"}}"
            f"QListWidget#{self._gallery.objectName()}::item:selected {{"
            f"  border-color: {tokens.ACCENT_PRIMARY};"
            f"  background-color: {tokens.BG_ACTIVE};"
            f"}}"
        )
        self._gallery.currentItemChanged.connect(self._on_item_selected)
        self._gallery.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._gallery.installEventFilter(self)
        splitter.addWidget(self._gallery)

        # Right: detail pane
        right_widget = QWidget(splitter)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self._lbl_detail_header = QLabel("Select an artifact to preview", right_widget)
        self._lbl_detail_header.setObjectName("lblEvidenceDetailHeader")
        self._lbl_detail_header.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px; font-weight: 600;"
        )
        right_layout.addWidget(self._lbl_detail_header)

        # Stacked viewer: image / text
        self._viewer_stack = QStackedWidget(right_widget)
        self._viewer_stack.setObjectName("evidenceViewerStack")

        # Page 0: Image viewer
        self._image_scroll = QScrollArea(self._viewer_stack)
        self._image_scroll.setWidgetResizable(True)
        self._image_scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {tokens.BG_ROOT}; border: 1px solid {tokens.BORDER}; "
            f"border-radius: {tokens.RADIUS}px; }}"
        )
        self._image_label = QLabel(self._image_scroll)
        self._image_label.setObjectName("evidenceImageLabel")
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setStyleSheet(f"background-color: {tokens.BG_ROOT};")
        self._image_scroll.setWidget(self._image_label)
        self._image_scroll.installEventFilter(self)
        self._image_scroll.viewport().installEventFilter(self)
        self._viewer_stack.addWidget(self._image_scroll)

        # Page 1: Text/JSON/Markdown viewer
        self._text_viewer = QTextEdit(self._viewer_stack)
        self._text_viewer.setObjectName("evidenceTextViewer")
        self._text_viewer.setAccessibleName("Artifact text viewer")
        self._text_viewer.setReadOnly(True)
        self._text_viewer.setStyleSheet(
            f"QTextEdit#{self._text_viewer.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_SM}px;"
            f"  font-family: monospace; font-size: 11px;"
            f"}}"
        )
        self._viewer_stack.addWidget(self._text_viewer)

        # Page 2: Markdown viewer
        self._md_viewer = QTextEdit(self._viewer_stack)
        self._md_viewer.setObjectName("evidenceMarkdownViewer")
        self._md_viewer.setAccessibleName("Artifact markdown viewer")
        self._md_viewer.setReadOnly(True)
        self._md_viewer.setStyleSheet(
            f"QTextEdit#{self._md_viewer.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"}}"
        )
        self._viewer_stack.addWidget(self._md_viewer)

        right_layout.addWidget(self._viewer_stack, 1)
        splitter.addWidget(right_widget)

        splitter.setSizes([400, 600])
        main_layout.addWidget(splitter, 1)

    # ── Public API ───────────────────────────────────────────────────────────

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.refresh_artifacts()

    def set_project(self, project_name: str, project_dir: Optional[Path] = None) -> None:
        self._current_project = project_name
        p_dir = project_dir or resolve_project_dir(project_name, self._workspace)
        self._project_dir = p_dir
        self._current_project_dir = p_dir
        if self._current_project_dir:
            self._store = RunStore(project_dir=self._current_project_dir, workspace_dir=self._workspace)
        self.refresh_artifacts()

    def clear_project(self) -> None:
        """Reset evidence view when no project is active."""
        self._current_project = None
        self._project_dir = None
        self._current_project_dir = None
        self._artifact_paths.clear()
        if hasattr(self, "_gallery"):
            self._gallery.clear()
        if hasattr(self, "_text_viewer"):
            self._text_viewer.clear()
        if hasattr(self, "_md_viewer"):
            self._md_viewer.clear()
        if hasattr(self, "_image_label"):
            self._image_label.clear()
        if hasattr(self, "_lbl_detail_header"):
            self._lbl_detail_header.setText("Select an artifact to preview")
        if hasattr(self, "_empty_label"):
            self._empty_label.setVisible(True)

    @Slot()
    def refresh_artifacts(self) -> None:
        """Collect artifacts from all runs for the current project."""
        self._artifact_paths.clear()
        self._gallery.clear()
        self._text_viewer.clear()
        self._md_viewer.clear()
        self._image_label.clear()
        self._lbl_detail_header.setText("Select an artifact to preview")

        if not self._current_project:
            self._lbl_summary.setText("No project selected.")
            return

        project_dir = getattr(self, "_current_project_dir", None) or resolve_project_dir(self._current_project, self._workspace)
        if not project_dir or not project_dir.is_dir():
            self._lbl_summary.setText(f"Project directory not found for '{self._current_project}'.")
            return

        # Collect from RunStore
        seen_paths: set = set()
        index = self._store.get_runs_index()
        for run_entry in index:
            run_id = run_entry.get("run_id", "")
            state = self._store.load(run_id)
            if not state:
                continue
            for step_id, rec in state.records.items():
                for art in rec.artifacts:
                    art_path_str = getattr(art, "path", str(art))
                    full_path = Path(art_path_str)
                    if not full_path.is_absolute():
                        full_path = project_dir / art_path_str
                    if full_path.is_file() and str(full_path) not in seen_paths:
                        seen_paths.add(str(full_path))
                        self._artifact_paths.append(full_path)

        # Also scan common evidence directories
        candidate_dirs = [
            project_dir / "Saved" / "GameForge" / "evidence",
            project_dir / "Saved" / "GameForge",
            project_dir / "reports",
        ]
        if self._workspace and (self._workspace / "reports").is_dir():
            candidate_dirs.append(self._workspace / "reports")

        for evidence_dir in candidate_dirs:
            if evidence_dir.is_dir():
                for f in sorted(evidence_dir.rglob("*")):
                    if f.is_file() and str(f) not in seen_paths:
                        ext = f.suffix.lower()
                        if ext in IMAGE_EXTS | JSON_EXTS | TEXT_EXTS | MARKDOWN_EXTS:
                            seen_paths.add(str(f))
                            self._artifact_paths.append(f)

        self._artifact_paths.sort(key=lambda p: p.name)
        self._populate_gallery()

    def _populate_gallery(self) -> None:
        filter_text = self._filter_combo.currentText()
        filtered = self._apply_filter_to_list(self._artifact_paths, filter_text)

        self._lbl_summary.setText(
            f"{len(filtered)} artifacts shown"
            + (f" (of {len(self._artifact_paths)} total)" if len(filtered) != len(self._artifact_paths) else "")
        )

        self._gallery.clear()
        for path in filtered:
            name = path.name
            ext = path.suffix.lower()
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, str(path))
            item.setSizeHint(QSize(140, 110))

            # Try to generate thumbnail for images
            if ext in IMAGE_EXTS:
                try:
                    pix = QPixmap(str(path))
                    if not pix.isNull():
                        item.setIcon(QIcon(pix.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                except Exception:
                    pass
            self._gallery.addItem(item)

    def _apply_filter_to_list(self, paths: List[Path], filter_text: str) -> List[Path]:
        if filter_text == "All":
            return paths
        elif filter_text == "Images":
            return [p for p in paths if p.suffix.lower() in IMAGE_EXTS]
        elif filter_text == "JSON":
            return [p for p in paths if p.suffix.lower() in JSON_EXTS]
        elif filter_text == "Reports / Docs":
            return [p for p in paths if p.suffix.lower() in MARKDOWN_EXTS]
        elif filter_text == "Logs":
            return [p for p in paths if p.suffix.lower() in TEXT_EXTS]
        else:
            standard_exts = IMAGE_EXTS | JSON_EXTS | TEXT_EXTS | MARKDOWN_EXTS
            return [p for p in paths if p.suffix.lower() not in standard_exts]

    @Slot(int)
    def _apply_filter(self, _index: int = 0) -> None:
        self._populate_gallery()

    @Slot(QListWidgetItem)
    def _on_item_double_clicked(self, item: Optional[QListWidgetItem]) -> None:
        if not item:
            return
        path_str = item.data(Qt.UserRole)
        if path_str:
            self.openFileRequested.emit(str(path_str))
            open_folder_in_file_manager(Path(path_str))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._gallery and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                item = self._gallery.currentItem()
                if item:
                    self._on_item_double_clicked(item)
                    return True
        elif hasattr(self, "_image_scroll") and (watched is self._image_scroll or (self._image_scroll.viewport() and watched is self._image_scroll.viewport())):
            if event.type() == QEvent.Resize:
                if hasattr(self, "_viewer_stack") and self._viewer_stack.currentIndex() == 0:
                    self._rescale_image()
        return super().eventFilter(watched, event)

    @Slot()
    def _on_item_selected(self, current: Optional[QListWidgetItem] = None, previous: Optional[QListWidgetItem] = None) -> None:
        if not current:
            return
        path_str = current.data(Qt.UserRole)
        if not path_str:
            return
        path = Path(path_str)
        ext = path.suffix.lower()

        self._lbl_detail_header.setText(f"{path.name}  ·  {_human_size(path)}")

        if ext in IMAGE_EXTS:
            self._show_image(path)
        elif ext in MARKDOWN_EXTS:
            self._show_markdown(path)
        elif ext in JSON_EXTS:
            self._show_json(path)
        else:
            self._show_text(path)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_viewer_stack") and self._viewer_stack.currentIndex() == 0:
            self._rescale_image()

    def _rescale_image(self) -> None:
        pix = getattr(self, "_current_pixmap", None)
        if pix and not pix.isNull():
            vp = self._image_scroll.viewport()
            available = vp.size() if vp else self._image_scroll.size()
            target_w = max(64, available.width() - 8)
            target_h = max(64, available.height() - 8)
            scaled = pix.scaled(
                target_w, target_h,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self._image_label.setPixmap(scaled)

    def _show_image(self, path: Path) -> None:
        pix = QPixmap(str(path))
        self._current_pixmap = pix
        if not pix.isNull():
            self._rescale_image()
        else:
            self._image_label.setText("Unable to load image.")
        self._viewer_stack.setCurrentIndex(0)

    def _show_json(self, path: Path) -> None:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
            formatted = json.dumps(data, indent=2)
            self._text_viewer.setPlainText(formatted)
        except Exception as e:
            self._text_viewer.setPlainText(f"Error reading JSON: {e}\n\n{path}")
        self._viewer_stack.setCurrentIndex(1)

    def _show_markdown(self, path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            self._md_viewer.setMarkdown(content)
        except Exception as e:
            self._md_viewer.setPlainText(f"Error reading Markdown: {e}")
        self._viewer_stack.setCurrentIndex(2)

    def _show_text(self, path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            self._text_viewer.setPlainText(content[:100_000])
        except Exception as e:
            self._text_viewer.setPlainText(f"Error reading file: {e}")
        self._viewer_stack.setCurrentIndex(1)


def _human_size(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return "? B"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
