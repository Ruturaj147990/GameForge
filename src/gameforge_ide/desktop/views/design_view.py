"""Design view for Studio UX v2 (spec §4.3, WI-4.6).

Displays:
- Header bar: Title, revision, validation state, History dropdown, Raw JSON, Build game
- Questions panel (shown when questions exist from prompt_to_gds or user)
- GDS Form (Overview, World, Things, Rules, Goals, Collapsible sub-sections)
- Revision history diff dialog and Raw JSON editor dialog
- Save (Ctrl+S) saving revision+1 via design.store.save
- Build game triggering Forge run and jumping to Build view
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..services.projects_service import GameSummary
from ..styles import tokens
from ..widgets.gds_form import GdsForm
from src.gameforge_ide.core.jobs import JobHandle, default_job_manager
from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.design.gds import GameDesignSpec
from src.gameforge_ide.design.patch import apply_patch, propose_patch, summarize_patch
from src.gameforge_ide.design.presets import PRESETS
import src.gameforge_ide.design.store as gds_store

logger = logging.getLogger(__name__)


class RawJsonDialog(QDialog):
    """Raw JSON editor with validation."""

    def __init__(self, spec: GameDesignSpec, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("rawJsonDialog")
        self.setAccessibleName("Raw JSON spec editor")
        self.setWindowTitle("Raw JSON Specification")
        self.setModal(True)
        self.resize(700, 560)
        self.setStyleSheet(
            f"QDialog#{self.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  border: 1px solid {tokens.BORDER};"
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_MD, tokens.SPACE_MD, tokens.SPACE_MD, tokens.SPACE_MD)
        layout.setSpacing(tokens.SPACE_SM)

        self._edit = QPlainTextEdit(self)
        self._edit.setObjectName("rawJsonEditor")
        self._edit.setPlainText(spec.model_dump_json(indent=2))
        self._edit.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE};"
            f"color: {tokens.TEXT_PRIMARY};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"font-family: monospace;"
            f"font-size: {tokens.FONT_BODY}px;"
        )
        layout.addWidget(self._edit, 1)

        self._err_lbl = QLabel(self)
        self._err_lbl.setStyleSheet(f"color: {tokens.ACCENT_ERROR}; font-size: {tokens.FONT_BODY_SM}px;")
        self._err_lbl.setVisible(False)
        layout.addWidget(self._err_lbl)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        btn_cancel = QPushButton("Close", self)
        btn_cancel.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px;"
            f"}}"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_apply = QPushButton("Apply Changes", self)
        btn_apply.setObjectName("btnApplyJson")
        btn_apply.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY};"
            f"  border: none; border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px; font-weight: 600;"
            f"}}"
        )
        btn_apply.clicked.connect(self._on_apply)
        btn_layout.addWidget(btn_apply)

        layout.addLayout(btn_layout)
        self.validated_spec: Optional[GameDesignSpec] = None

    def _on_apply(self) -> None:
        text = self._edit.toPlainText().strip()
        try:
            parsed = GameDesignSpec.model_validate_json(text)
            self.validated_spec = parsed
            self.accept()
        except Exception as exc:
            self._err_lbl.setText(f"JSON Validation Error: {exc}")
            self._err_lbl.setVisible(True)


class DiffDialog(QDialog):
    """Revision diff dialog displaying patch operations."""

    def __init__(self, rev_from: int, rev_to: int, ops: List[Dict[str, Any]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("diffDialog")
        self.setAccessibleName("Revision diff dialog")
        self.setWindowTitle(f"Revisions Diff: r{rev_from} → r{rev_to}")
        self.setModal(True)
        self.resize(650, 420)
        self.setStyleSheet(
            f"QDialog#{self.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  border: 1px solid {tokens.BORDER};"
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_MD, tokens.SPACE_MD, tokens.SPACE_MD, tokens.SPACE_MD)
        layout.setSpacing(tokens.SPACE_SM)

        title = QLabel(f"Changes between revision {rev_from} and revision {rev_to} ({len(ops)} operations):", self)
        title.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px; font-weight: 600;")
        layout.addWidget(title)

        table = QTableWidget(self)
        table.setObjectName("diffOpsTable")
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Operation", "Field Path", "Previous Value", "New Value"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"}}"
        )

        table.setRowCount(len(ops))
        for r, op in enumerate(ops):
            table.setItem(r, 0, QTableWidgetItem(str(op.get("op", ""))))
            table.setItem(r, 1, QTableWidgetItem(str(op.get("path", ""))))
            table.setItem(r, 2, QTableWidgetItem(str(op.get("from", "—"))))
            table.setItem(r, 3, QTableWidgetItem(str(op.get("value", "—"))))
        layout.addWidget(table, 1)

        btn_close = QPushButton("Close", self)
        btn_close.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px;"
            f"}}"
        )
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)


def parse_question_options(question: str) -> List[str]:
    """Parse discrete choices from a question string if present; fallback to ['Yes', 'No']."""
    q_clean = question.strip().rstrip("?").strip()

    # 1. Colon pattern: e.g. 'Which camera style: third person, first person, or top-down'
    if ":" in q_clean:
        _, after_colon = q_clean.split(":", 1)
        parts = re.split(r",\s*(?:or\s+)?|\s+or\s+", after_colon.strip())
        parts = [p.strip().strip(".").strip() for p in parts if p.strip()]
        if len(parts) >= 2:
            return [re.sub(r"^(?:a|an|the)\s+", "", p, flags=re.IGNORECASE).capitalize() for p in parts]

    # 2. Check for 'or' pattern
    if re.search(r"\bor\b", q_clean, re.IGNORECASE):
        pivots = [
            r"\b(?:play\s+as|act\s+as|as)\s+(?:a|an|the)?\s*",
            r"\b(?:between)\s+",
            r"\b(?:prefer|choose|pick)\s+(?:a|an|the)?\s*",
            r"\b(?:want|like|feature|include|use|have)\s+(?:to\s+)?(?:be\s+)?(?:add\s+)?(?:a|an|the)?\s*",
            r"\b(?:should\s+(?:the\s+)?\w+\s+(?:be\s+)?)",
            r"\b(?:is\s+(?:the\s+)?\w+\s+(?:be\s+)?)",
            r"\b(?:are\s+(?:the\s+)?\w+\s+)",
            r"\b(?:will\s+(?:the\s+)?\w+\s+be\s+)",
            r"\b(?:either)\s+",
            r"\b(?:be)\s+(?:a|an|the)?\s*",
            r"\b(?:is\s+it)\s+",
        ]

        for pivot in pivots:
            m = re.search(pivot + r"(.+)$", q_clean, re.IGNORECASE)
            if m:
                rest = m.group(1).strip()
                if re.search(r"\bor\b", rest, re.IGNORECASE):
                    parts = re.split(r",\s*(?:or\s+)?|\s+or\s+", rest, flags=re.IGNORECASE)
                    parts = [re.sub(r"^(?:a|an|the)\s+", "", p.strip(), flags=re.IGNORECASE) for p in parts if p.strip()]
                    if len(parts) >= 2 and all(0 < len(p) <= 35 for p in parts):
                        return [p.capitalize() if p.islower() else p for p in parts]

        # General concise question fallback: e.g. "First person or third person?"
        if q_clean.count(" ") <= 8:
            parts = re.split(r",\s*(?:or\s+)?|\s+or\s+", q_clean, flags=re.IGNORECASE)
            parts = [re.sub(r"^(?:a|an|the)\s+", "", p.strip(), flags=re.IGNORECASE) for p in parts if p.strip()]
            if len(parts) >= 2 and all(0 < len(p) <= 35 for p in parts):
                return [p.capitalize() if p.islower() else p for p in parts]

    return ["Yes", "No"]


class DesignView(QWidget):
    """Design view implementation for Studio UX (spec §4.3, WI-4.6)."""

    buildRequested = Signal(str)        # (project_name) -> trigger Build view
    projectChanged = Signal(str)        # (project_name)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("designView")
        self.setAccessibleName("GameForge Design View")

        self._current_spec: Optional[GameDesignSpec] = None
        self._current_project: Optional[str] = None
        self._is_dirty: bool = False
        self._job_manager = default_job_manager()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(tokens.SPACE_MD)

        # ── 1. Top Action Header ──────────────────────────────────────────────
        header_layout = QHBoxLayout()
        header_layout.setSpacing(tokens.SPACE_MD)

        # Title & Revision & Status label
        self._lbl_status = QLabel("No game loaded", self)
        self._lbl_status.setObjectName("lblDesignStatus")
        self._lbl_status.setAccessibleName("Design validation and revision status")
        self._lbl_status.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_HEADING_SM}px; font-weight: 700;"
        )
        header_layout.addWidget(self._lbl_status)

        # Unsaved changes dot
        self._lbl_dirty = QLabel("● Unsaved", self)
        self._lbl_dirty.setObjectName("lblDesignDirty")
        self._lbl_dirty.setStyleSheet(f"color: {tokens.ACCENT_WARNING}; font-size: {tokens.FONT_BODY_SM}px;")
        self._lbl_dirty.setVisible(False)
        header_layout.addWidget(self._lbl_dirty)

        header_layout.addStretch(1)

        # Save button
        self._btn_save = QPushButton("Save (Ctrl+S)", self)
        self._btn_save.setObjectName("btnDesignSave")
        self._btn_save.setCursor(Qt.PointingHandCursor)
        self._btn_save.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        self._btn_save.clicked.connect(self.save_spec)
        header_layout.addWidget(self._btn_save)

        # History dropdown button
        self._btn_history = QPushButton("History ▾", self)
        self._btn_history.setObjectName("btnDesignHistory")
        self._btn_history.setCursor(Qt.PointingHandCursor)
        self._btn_history.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        self._btn_history.clicked.connect(self._show_history_menu)
        header_layout.addWidget(self._btn_history)

        # Raw JSON button
        self._btn_raw_json = QPushButton("Raw JSON", self)
        self._btn_raw_json.setObjectName("btnDesignRawJson")
        self._btn_raw_json.setCursor(Qt.PointingHandCursor)
        self._btn_raw_json.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        self._btn_raw_json.clicked.connect(self._show_raw_json_dialog)
        header_layout.addWidget(self._btn_raw_json)

        # Build game button (Primary)
        self._btn_build = QPushButton("Build game", self)
        self._btn_build.setObjectName("btnDesignBuild")
        self._btn_build.setAccessibleName("Build game from design")
        self._btn_build.setCursor(Qt.PointingHandCursor)
        self._btn_build.setFixedHeight(30)
        self._btn_build.setStyleSheet(
            f"QPushButton#{self._btn_build.objectName()} {{"
            f"  background-color: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY};"
            f"  border: none; border-radius: {tokens.RADIUS}px;"
            f"  padding: 0 {tokens.SPACE_LG}px; font-weight: 600; font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton#{self._btn_build.objectName()}:hover {{ background-color: {tokens.ACCENT_HOVER}; }}"
            f"QPushButton#{self._btn_build.objectName()}:disabled {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_MUTED};"
            f"}}"
        )
        self._btn_build.clicked.connect(self.build_game)
        header_layout.addWidget(self._btn_build)

        main_layout.addLayout(header_layout)

        # ── 2. Questions Panel ────────────────────────────────────────────────
        self._questions_panel = QFrame(self)
        self._questions_panel.setObjectName("designQuestionsPanel")
        self._questions_panel.setAccessibleName("Design clarification questions")
        self._questions_panel.setStyleSheet(
            f"QFrame#{self._questions_panel.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.ACCENT_HOVER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_SM}px;"
            f"}}"
        )
        self._questions_layout = QVBoxLayout(self._questions_panel)
        self._questions_layout.setContentsMargins(10, 8, 10, 8)
        self._questions_layout.setSpacing(6)
        self._questions_panel.setVisible(False)
        main_layout.addWidget(self._questions_panel)

        # ── 2b. Change Request Panel (WI-8.1) ──────────────────────────────────
        self._pending_change_ops: List[Dict[str, Any]] = []
        self._change_panel = QFrame(self)
        self._change_panel.setObjectName("designChangePanel")
        self._change_panel.setAccessibleName("Change request panel")
        self._change_panel.setStyleSheet(
            f"QFrame#{self._change_panel.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_SM}px;"
            f"}}"
        )
        self._change_layout = QVBoxLayout(self._change_panel)
        self._change_layout.setContentsMargins(10, 8, 10, 8)
        self._change_layout.setSpacing(6)

        row_req = QHBoxLayout()
        self._txt_change = QLineEdit(self._change_panel)
        self._txt_change.setObjectName("txtDesignChangeRequest")
        self._txt_change.setPlaceholderText("Change this game… (e.g. make guards faster, add a hazard area, make it night)")
        self._txt_change.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px 10px; font-size: {tokens.FONT_BODY}px;"
            f"}}"
        )
        self._txt_change.returnPressed.connect(self._on_propose_change)
        row_req.addWidget(self._txt_change, 1)

        self._btn_preview_change = QPushButton("Preview change", self._change_panel)
        self._btn_preview_change.setObjectName("btnDesignPreviewChange")
        self._btn_preview_change.setCursor(Qt.PointingHandCursor)
        self._btn_preview_change.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_MD}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        self._btn_preview_change.clicked.connect(self._on_propose_change)
        row_req.addWidget(self._btn_preview_change)

        self._change_layout.addLayout(row_req)

        self._diff_preview_box = QFrame(self._change_panel)
        self._diff_preview_box.setObjectName("designDiffPreviewBox")
        diff_box_layout = QVBoxLayout(self._diff_preview_box)
        diff_box_layout.setContentsMargins(0, 4, 0, 0)
        diff_box_layout.setSpacing(6)

        self._lbl_diff_preview = QLabel(self._diff_preview_box)
        self._lbl_diff_preview.setObjectName("lblDesignDiffPreview")
        self._lbl_diff_preview.setStyleSheet(
            f"color: {tokens.ACCENT_PRIMARY}; font-size: {tokens.FONT_BODY_SM}px;"
        )
        self._lbl_diff_preview.setWordWrap(True)
        diff_box_layout.addWidget(self._lbl_diff_preview)

        row_actions = QHBoxLayout()
        row_actions.addStretch(1)

        self._btn_apply_change = QPushButton("Apply (new revision)", self._diff_preview_box)
        self._btn_apply_change.setObjectName("btnDesignApplyChange")
        self._btn_apply_change.setCursor(Qt.PointingHandCursor)
        self._btn_apply_change.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE}; color: {tokens.ACCENT_SUCCESS};"
            f"  border: 1px solid {tokens.ACCENT_SUCCESS}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px; font-weight: 600;"
            f"}}"
        )
        self._btn_apply_change.clicked.connect(self._on_apply_change)
        row_actions.addWidget(self._btn_apply_change)

        self._btn_rebuild_changes = QPushButton("Rebuild changes", self._diff_preview_box)
        self._btn_rebuild_changes.setObjectName("btnDesignRebuildChanges")
        self._btn_rebuild_changes.setCursor(Qt.PointingHandCursor)
        self._btn_rebuild_changes.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY};"
            f"  border: none; border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_LG}px; font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.ACCENT_HOVER}; }}"
        )
        self._btn_rebuild_changes.clicked.connect(self._on_rebuild_changes)
        row_actions.addWidget(self._btn_rebuild_changes)

        diff_box_layout.addLayout(row_actions)
        self._diff_preview_box.setVisible(False)
        self._change_layout.addWidget(self._diff_preview_box)

        main_layout.addWidget(self._change_panel)

        # ── 3. Scrollable Form Container ──────────────────────────────────────
        scroll = QScrollArea(self)
        scroll.setObjectName("designScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea#{scroll.objectName()} {{"
            f"  background-color: transparent;"
            f"  border: none;"
            f"}}"
        )

        self._form = GdsForm(scroll)
        self._form.changed.connect(self._on_form_changed)
        self._form.validationChanged.connect(self._on_validation_changed)
        scroll.setWidget(self._form)
        main_layout.addWidget(scroll, 1)

        # Shortcut Ctrl+S
        self._shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self._shortcut_save.activated.connect(self.save_spec)

    # ── Public API ───────────────────────────────────────────────────────────

    def open_draft(self, gds: GameDesignSpec, questions: Optional[List[str]] = None) -> None:
        """Open an in-memory draft (e.g. from Home's prompt_to_gds)."""
        self._current_spec = gds
        self._current_project = gds.meta.project_name or gds.meta.title
        self._is_dirty = True
        self._lbl_dirty.setVisible(True)

        self._form.set_spec(gds)
        self._render_questions(questions or [])
        self._update_header_status(is_valid=True, errors=[])

    def load_project(self, project_name: str) -> bool:
        """Load game.gds.json for project_name."""
        p_root = get_settings().projects_root
        if not p_root:
            return False
        p_dir = Path(p_root) / project_name
        loaded = gds_store.load(p_dir)
        if not loaded:
            return False

        self._current_project = project_name
        self._current_spec = loaded
        self._is_dirty = False
        self._lbl_dirty.setVisible(False)
        self._questions_panel.setVisible(False)

        self._form.set_spec(loaded)
        self._update_header_status(is_valid=True, errors=[])
        return True

    def save_spec(self) -> bool:
        """Save current form spec with revision+1."""
        try:
            spec = self._form.get_spec()
        except Exception as exc:
            logger.error("Failed to get spec from form: %s", exc)
            return False
        if not spec or not self._current_project:
            return False

        p_root = get_settings().projects_root
        if not p_root:
            return False
        p_dir = Path(p_root) / self._current_project

        spec.meta.revision += 1
        try:
            gds_store.save(p_dir, spec)
            self._current_spec = spec
            self._is_dirty = False
            self._lbl_dirty.setVisible(False)
            self._update_header_status(is_valid=True, errors=[])
            return True
        except gds_store.RevisionConflict as exc:
            reply = QMessageBox.question(
                self,
                "Revision Conflict",
                f"{exc}\n\nWould you like to reload the stored revision?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self.load_project(self._current_project)
            return False
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", f"Failed to save design spec:\n{exc}")
            return False

    def build_game(self) -> None:
        """Save spec and trigger Forge run."""
        if not self._current_project or not self._current_spec:
            return
        if self._is_dirty:
            if not self.save_spec():
                return

        # Show run approval scope dialog with impact analysis (WI-8.2)
        impact_summary = ""
        p_root = get_settings().projects_root
        if p_root and self._current_project:
            p_dir = Path(p_root) / self._current_project
            try:
                from src.gameforge_ide.forge.store import RunStore
                store = RunStore(project_dir=p_dir, workspace_dir=p_dir.parent)
                prev_state = store.latest_for_project(p_dir)
                if prev_state and self._current_spec:
                    from src.gameforge_ide.composer.compose import compose
                    from src.gameforge_ide.composer.plan import composition_to_run_spec
                    from src.gameforge_ide.forge.impact import impact
                    comp = compose(self._current_spec, str(p_dir))
                    new_spec = composition_to_run_spec(comp, str(p_dir.parent), str(p_dir), origin="change_request")
                    rep = impact(prev_state, new_spec)
                    impact_summary = f"{rep.format_summary()}\n\n"
            except Exception as exc:
                logger.debug("Failed to calculate impact summary: %s", exc)

        msg = (
            f"{impact_summary}"
            f"Approval Scope for '{self._current_project}':\n\n"
            f"• Project Folder: {get_settings().projects_root}/{self._current_project}\n"
            f"• Unreal Editor operations (compile C++, assemble level, lighting, package)\n\n"
            f"Do you want to start this Forge run now?"
        )
        reply = QMessageBox.question(self, "Approve Forge Run", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            print(f"[GameForge Studio] Forge run approved for '{self._current_project}' — launching build DAG...", flush=True)
            self.buildRequested.emit(self._current_project)

    # ── Internal Slots & Helpers ─────────────────────────────────────────────

    @Slot()
    def _on_form_changed(self) -> None:
        self._is_dirty = True
        self._lbl_dirty.setVisible(True)

    @Slot(bool, list)
    def _on_validation_changed(self, is_valid: bool, errors: List[str]) -> None:
        self._update_header_status(is_valid, errors)

    def _update_header_status(self, is_valid: bool, errors: List[str]) -> None:
        title = self._current_project or "Untitled"
        rev = self._current_spec.meta.revision if (self._current_spec and self._current_spec.meta) else 1
        if is_valid:
            status_text = f"{title} · revision {rev} · <font color='{tokens.ACCENT_SUCCESS}'>✓ valid</font>"
            self._btn_build.setEnabled(True)
        else:
            n = len(errors)
            status_text = f"{title} · revision {rev} · <font color='{tokens.ACCENT_ERROR}'>✕ {n} problem{'s' if n != 1 else ''}</font>"
            self._btn_build.setEnabled(False)
        self._lbl_status.setText(status_text)

    def _render_questions(self, questions: List[str]) -> None:
        while self._questions_layout.count() > 0:
            item = self._questions_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                while item.layout().count() > 0:
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        self._answered_questions: Dict[str, str] = {}
        self._total_questions = len(questions)

        if not questions:
            self._questions_panel.setVisible(False)
            return

        lbl_q_head = QLabel(f"Clarification Questions ({len(questions)}):", self._questions_panel)
        lbl_q_head.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: 600; font-size: {tokens.FONT_BODY}px;")
        self._lbl_q_head = lbl_q_head
        self._questions_layout.addWidget(lbl_q_head)

        for q in questions:
            row_widget = QWidget(self._questions_panel)
            row_widget.setObjectName("designQuestionRow")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(8)

            q_lbl = QLabel(f"• {q}", row_widget)
            q_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
            q_lbl.setWordWrap(True)
            row_layout.addWidget(q_lbl, 1)

            actions_widget = QWidget(row_widget)
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(6)

            options = parse_question_options(q)
            for opt in options:
                btn = QPushButton(opt, actions_widget)
                if opt.lower() == "yes":
                    color = tokens.ACCENT_SUCCESS
                elif opt.lower() == "no":
                    color = tokens.ACCENT_ERROR
                else:
                    color = tokens.ACCENT_PRIMARY

                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet(
                    f"QPushButton {{"
                    f"  background-color: {tokens.BG_SURFACE}; color: {color};"
                    f"  border: 1px solid {tokens.BORDER}; border-radius: 4px;"
                    f"  padding: 3px 10px; font-size: {tokens.FONT_BODY_SM}px; font-weight: 500;"
                    f"}}"
                    f"QPushButton:hover {{"
                    f"  background-color: {tokens.BG_PANEL}; border-color: {color};"
                    f"}}"
                )
                btn.clicked.connect(
                    lambda _, a=opt, r=row_widget, act=actions_widget, l=q_lbl, qu=q: self._answer_question(
                        qu, a, r, act, l
                    )
                )
                actions_layout.addWidget(btn)

            txt_other = QLineEdit(actions_widget)
            txt_other.setPlaceholderText("Other…")
            txt_other.setFixedWidth(130)
            txt_other.setStyleSheet(
                f"QLineEdit {{"
                f"  background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
                f"  border: 1px solid {tokens.BORDER}; border-radius: 4px;"
                f"  padding: 3px 8px; font-size: {tokens.FONT_BODY_SM}px;"
                f"}}"
                f"QLineEdit:focus {{"
                f"  border-color: {tokens.ACCENT_PRIMARY};"
                f"}}"
            )

            btn_submit = QPushButton("Submit", actions_widget)
            btn_submit.setCursor(Qt.PointingHandCursor)
            btn_submit.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY};"
                f"  border: none; border-radius: 4px;"
                f"  padding: 3px 10px; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: {tokens.ACCENT_HOVER};"
                f"}}"
            )

            def _make_submit(t=txt_other, r=row_widget, act=actions_widget, l=q_lbl, qu=q):
                def _submit():
                    val = t.text().strip()
                    if val:
                        self._answer_question(qu, val, r, act, l)
                return _submit

            submit_fn = _make_submit(txt_other, row_widget, actions_widget, q_lbl, q)
            btn_submit.clicked.connect(submit_fn)
            txt_other.returnPressed.connect(submit_fn)

            actions_layout.addWidget(txt_other)
            actions_layout.addWidget(btn_submit)

            row_layout.addWidget(actions_widget)
            self._questions_layout.addWidget(row_widget)

        self._questions_panel.setVisible(True)

    def _answer_question(
        self,
        question: str,
        answer: str,
        row_widget: QWidget,
        actions_widget: QWidget,
        label: QLabel,
    ) -> None:
        actions_widget.setVisible(False)

        badge = QLabel(f"✓ {answer}", row_widget)
        badge.setStyleSheet(
            f"color: {tokens.ACCENT_SUCCESS}; font-weight: 600; font-size: {tokens.FONT_BODY_SM}px;"
            f"background-color: {tokens.BG_SURFACE}; border: 1px solid {tokens.ACCENT_SUCCESS};"
            f"border-radius: 4px; padding: 2px 8px;"
        )
        row_widget.layout().addWidget(badge)

        label.setText(f"• <s>{question}</s>")
        label.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_BODY_SM}px;")

        if not hasattr(self, "_answered_questions"):
            self._answered_questions = {}
        self._answered_questions[question] = answer

        self._is_dirty = True
        self._lbl_dirty.setVisible(True)

        if hasattr(self, "_lbl_q_head") and hasattr(self, "_total_questions") and self._total_questions > 0:
            answered_count = len(self._answered_questions)
            if answered_count >= self._total_questions:
                self._lbl_q_head.setText(f"Clarification Questions ({answered_count}/{self._total_questions} answered ✓):")
                self._lbl_q_head.setStyleSheet(
                    f"color: {tokens.ACCENT_SUCCESS}; font-weight: 600; font-size: {tokens.FONT_BODY}px;"
                )
            else:
                self._lbl_q_head.setText(f"Clarification Questions ({answered_count}/{self._total_questions} answered):")

        if hasattr(self, "_form") and self._form and hasattr(self._form, "_edit_pitch"):
            curr_pitch = self._form._edit_pitch.toPlainText().strip()
            addition = f" [{answer}]"
            if answer.lower() not in curr_pitch.lower() and len(curr_pitch) + len(addition) <= 270:
                self._form._edit_pitch.setPlainText(f"{curr_pitch}{addition}")

    def _dismiss_question(self, label: QLabel) -> None:
        label.setText(f"<s>{label.text()}</s> (Answered)")
        label.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_BODY_SM}px;")
        self._is_dirty = True
        self._lbl_dirty.setVisible(True)

    @Slot()
    def _show_history_menu(self) -> None:
        if not self._current_project:
            return
        p_root = get_settings().projects_root
        if not p_root:
            return
        p_dir = Path(p_root) / self._current_project
        revs = gds_store.history(p_dir)
        if not revs:
            QMessageBox.information(self, "No History", "No previous revisions preserved for this game.")
            return

        menu = QMenu(self)
        menu.setObjectName("designHistoryMenu")
        for r in reversed(revs):
            act = menu.addAction(f"Revision {r}")
            act.triggered.connect(lambda _, rev=r: self._show_diff_dialog(p_dir, rev))
        menu.exec(self._btn_history.mapToGlobal(self._btn_history.rect().bottomLeft()))

    def _show_diff_dialog(self, p_dir: Path, target_rev: int) -> None:
        old_spec = gds_store.load_revision(p_dir, target_rev)
        curr_spec = self._form.get_spec() or self._current_spec
        if not old_spec or not curr_spec:
            return
        ops = gds_store.diff(old_spec, curr_spec)
        curr_rev = curr_spec.meta.revision if curr_spec.meta else 1
        dlg = DiffDialog(target_rev, curr_rev, ops, self)
        dlg.exec()

    @Slot()
    def _show_raw_json_dialog(self) -> None:
        spec = self._form.get_spec() or self._current_spec
        if not spec:
            return
        dlg = RawJsonDialog(spec, self)
        if dlg.exec() == QDialog.Accepted and dlg.validated_spec:
            self._current_spec = dlg.validated_spec
            self._form.set_spec(dlg.validated_spec)
            self._is_dirty = True
            self._lbl_dirty.setVisible(True)

    def _get_model_caller(self):
        import os
        if "PYTEST_CURRENT_TEST" in os.environ:
            return None
        try:
            from ..providers.ollama_provider import OllamaProvider
            settings = get_settings()
            provider = OllamaProvider(host=settings.ollama_url.replace("http://", "").replace("https://", ""))
            model = settings.model_for("design")

            def _caller(task: str, prompt: str) -> str:
                sys_prompt = (
                    "You are a GameForge GDS patch assistant. Generate RFC 6902 JSON patch ops "
                    "to update the GameDesignSpec based on the user request. "
                    "Return a JSON object with keys: ops (array of {op, path, value}), summary (string), questions (array of string)."
                )
                raw_json = provider.complete_json(
                    model,
                    sys_prompt,
                    prompt,
                    {
                        "type": "object",
                        "properties": {
                            "ops": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "op": {"type": "string", "enum": ["add", "remove", "replace"]},
                                        "path": {"type": "string"},
                                        "value": {}
                                    },
                                    "required": ["op", "path"]
                                }
                            },
                            "summary": {"type": "string"},
                            "questions": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["ops", "summary"]
                    }
                )
                return raw_json or "{}"

            return _caller
        except Exception:
            return None

    @Slot()
    def _on_propose_change(self) -> None:
        text = self._txt_change.text().strip()
        if not text:
            return
        try:
            curr_spec = self._form.get_spec() or self._current_spec
        except Exception as exc:
            logger.error("Failed to get spec from form: %s", exc)
            curr_spec = self._current_spec
        if not curr_spec:
            return
        prop = propose_patch(curr_spec, text, model_caller=self._get_model_caller())
        if prop.status == "OK" and prop.ops:
            self._pending_change_ops = prop.ops
            sentences = summarize_patch(curr_spec, prop.ops)
            summary_txt = "<b>Diff preview:</b><br/>" + "<br/>".join(f"• {s}" for s in sentences)
            self._lbl_diff_preview.setText(summary_txt)
            self._btn_apply_change.setEnabled(True)
            self._btn_rebuild_changes.setEnabled(True)
            self._diff_preview_box.setVisible(True)
        else:
            msg = prop.summary or "Could not generate patch."
            if prop.questions:
                msg += "<br/>" + "<br/>".join(f"• {q}" for q in prop.questions)
            self._lbl_diff_preview.setText(f"<font color='{tokens.ACCENT_ERROR}'>{msg}</font>")
            self._btn_apply_change.setEnabled(False)
            self._btn_rebuild_changes.setEnabled(False)
            self._diff_preview_box.setVisible(True)

    @Slot()
    def _on_apply_change(self) -> None:
        if not self._pending_change_ops:
            return
        curr_spec = self._form.get_spec() or self._current_spec
        if not curr_spec:
            return
        try:
            patched = apply_patch(curr_spec, self._pending_change_ops)
            self._current_spec = patched
            self._form.set_spec(patched)
            self._is_dirty = False
            self._lbl_dirty.setVisible(False)
            if self._current_project:
                p_root = get_settings().projects_root
                if p_root:
                    p_dir = Path(p_root) / self._current_project
                    gds_store.save(p_dir, patched)
            self._diff_preview_box.setVisible(False)
            self._txt_change.clear()
            self._pending_change_ops = []
        except Exception as exc:
            QMessageBox.warning(self, "Patch Error", f"Could not apply patch: {exc}")

    @Slot()
    def _on_rebuild_changes(self) -> None:
        self._on_apply_change()
        self.build_game()
