"""Home view for Studio UX v2 (spec §4.1, WI-4.4).

Displays:
- Hero "Make a game" with prompt box (Enter=newline, Ctrl+Enter=Design it)
- Preset chips pre-filling the prompt
- "Design it →" running prompt_to_gds on JobManager with status & cancel
- Recent games grid (top 6 by updated_at)
- Readiness card fed by SystemsService
"""
from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QKeyEvent, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..services.projects_service import GameSummary, list_games
from ..services.systems_service import SystemsService
from ..styles import tokens
from src.gameforge_ide.core.jobs import JobHandle, default_job_manager
from src.gameforge_ide.core.systems import SystemRow, SystemsSnapshot, probe_all
from src.gameforge_ide.design.presets import PRESETS

logger = logging.getLogger(__name__)


class PromptTextEdit(QPlainTextEdit):
    """Prompt box where Enter adds a newline and Ctrl+Enter requests design."""

    designRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("homePromptInput")
        self.setAccessibleName("Game design prompt input")
        self.setPlaceholderText(
            'Describe your game… e.g. "a third-person forest adventure where I collect 5 relics while avoiding guards"'
        )
        self.setFixedHeight(110)
        self.setStyleSheet(
            f"QPlainTextEdit#{self.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"  line-height: 1.4;"
            f"}}"
            f"QPlainTextEdit#{self.objectName()}:focus {{"
            f"  border: 1px solid {tokens.BORDER_FOCUS};"
            f"}}"
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            self.designRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class PresetChip(QPushButton):
    """Clickable chip prefilling the prompt box."""

    def __init__(self, title: str, preset_id: str, prompt_text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(title, parent)
        self.preset_id = preset_id
        self.prompt_text = prompt_text
        self.setObjectName(f"presetChip_{preset_id}")
        self.setAccessibleName(f"Preset chip {title}")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton#{self.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: 14px;"
            f"  padding: {tokens.SPACE_XS}px {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self.objectName()}:hover {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border-color: {tokens.ACCENT_HOVER};"
            f"}}"
            f"QPushButton#{self.objectName()}:pressed {{"
            f"  background-color: {tokens.BG_ACTIVE};"
            f"}}"
        )


class RecentGameCard(QFrame):
    """Clickable card displaying a recent game with thumbnail and status."""

    clicked = Signal(str)

    def __init__(self, game: GameSummary, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game = game
        self.setObjectName(f"recentGameCard_{game.name}")
        self.setAccessibleName(f"Recent game {game.title}")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(140, 150)
        self.setStyleSheet(
            f"QFrame#{self.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"}}"
            f"QFrame#{self.objectName()}:hover {{"
            f"  border-color: {tokens.ACCENT_PRIMARY};"
            f"  background-color: {tokens.BG_HOVER};"
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Thumbnail
        self._thumb_lbl = QLabel(self)
        self._thumb_lbl.setFixedSize(126, 78)
        self._thumb_lbl.setStyleSheet(
            f"background-color: {tokens.BG_PANEL};"
            f"border-radius: 4px;"
        )
        self._thumb_lbl.setAlignment(Qt.AlignCenter)
        self._load_thumbnail(game.thumbnail_path)
        layout.addWidget(self._thumb_lbl)

        # Title
        title_lbl = QLabel(game.title, self)
        title_lbl.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY};"
            f"font-size: {tokens.FONT_BODY}px;"
            f"font-weight: 600;"
        )
        title_lbl.setFixedHeight(18)
        layout.addWidget(title_lbl)

        # Status badge & time
        status_text = self._format_status(game)
        status_lbl = QLabel(status_text, self)
        status_lbl.setStyleSheet(
            f"color: {tokens.TEXT_MUTED};"
            f"font-size: {tokens.FONT_BODY_SM}px;"
        )
        layout.addWidget(status_lbl)
        layout.addStretch(1)

    def _load_thumbnail(self, path: Optional[Any]) -> None:
        if path and str(path):
            pm = QPixmap(str(path))
            if not pm.isNull():
                scaled = pm.scaled(126, 78, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self._thumb_lbl.setPixmap(scaled)
                return
        # Placeholder
        self._thumb_lbl.setText("🎮")

    def _format_status(self, game: GameSummary) -> str:
        status_part = game.last_run_status or "—"
        if status_part == "DONE":
            status_part = "PASS"
        time_part = ""
        if game.updated_at > 0:
            diff_s = max(0.0, time.time() - game.updated_at)
            if diff_s < 3600:
                time_part = f"{int(diff_s // 60)}m"
            elif diff_s < 86400:
                time_part = f"{int(diff_s // 3600)}h"
            else:
                time_part = f"{int(diff_s // 86400)}d"
        return f"{status_part} {time_part}".strip()

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.game.name)
            event.accept()
            return
        super().mousePressEvent(event)


class ReadinessRowWidget(QWidget):
    """Row displaying a single readiness probe outcome."""

    fixActionRequested = Signal(str)

    def __init__(self, row: SystemRow, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(f"readinessRow_{row.key}")
        self.setAccessibleName(f"Readiness item {row.key}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(tokens.SPACE_SM)

        # Dot
        dot_color = tokens.ACCENT_SUCCESS if row.state == "ok" else (
            tokens.ACCENT_WARNING if row.state == "degraded" else tokens.ACCENT_ERROR
        )
        dot_lbl = QLabel("●", self)
        dot_lbl.setStyleSheet(f"color: {dot_color}; font-size: 11px;")
        layout.addWidget(dot_lbl)

        # Key title + summary
        label_text = f"{row.key.capitalize()}: {row.summary}"
        if row.key == "engine":
            label_text = f"Unreal Engine {row.summary}"
        elif row.key == "ollama":
            label_text = f"Ollama · {row.summary}"
        elif row.key == "disk":
            label_text = f"Disk {row.summary}"
        elif row.key == "hosted":
            label_text = f"Hosted models: {row.summary}"

        text_lbl = QLabel(label_text, self)
        text_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        layout.addWidget(text_lbl, 1)

        if row.fix_action:
            btn = QPushButton("Set up", self)
            btn.setObjectName(f"btn_fix_{row.key}")
            btn.setCursor(Qt.PointingHandCursor)
            action_key = str(row.fix_action)
            btn.clicked.connect(lambda checked=False, act=action_key: self.fixActionRequested.emit(act))
            btn.setToolTip(f"Set up {row.key.capitalize()}")
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background: transparent;"
                f"  color: {tokens.ACCENT_HOVER};"
                f"  border: 1px solid {tokens.BORDER};"
                f"  border-radius: 4px;"
                f"  padding: 1px 6px;"
                f"  font-size: {tokens.FONT_BODY_SM}px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: {tokens.BG_HOVER};"
                f"}}"
            )
            layout.addWidget(btn)


class HomeView(QWidget):
    """Home view implementation for Studio UX."""

    designReady = Signal(object, list)       # (GameDesignSpec, questions)
    projectSelected = Signal(str)             # (project_name)
    openAssistantRequested = Signal()         # Request to open assistant panel
    fixActionRequested = Signal(str)          # ("start_ollama" | "set_engine" | "open_hosted")

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("homeView")
        self.setAccessibleName("GameForge Home View")

        self._active_job: Optional[JobHandle] = None
        self._job_manager = default_job_manager()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 28, 32, 28)
        main_layout.setSpacing(tokens.SPACE_MD)

        # ── 1. Hero Section ──────────────────────────────────────────────────
        hero_layout = QVBoxLayout()
        hero_layout.setSpacing(tokens.SPACE_SM)

        title_lbl = QLabel("Make a game", self)
        title_lbl.setObjectName("homeTitle")
        title_lbl.setAccessibleName("Make a game hero title")
        title_lbl.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY};"
            f"font-size: {tokens.FONT_HEADING}px;"
            f"font-weight: 700;"
        )
        hero_layout.addWidget(title_lbl)

        # Prompt Box
        self._prompt_input = PromptTextEdit(self)
        self._prompt_input.designRequested.connect(self._on_design_it_clicked)
        hero_layout.addWidget(self._prompt_input)

        # Preset Chips
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(tokens.SPACE_SM)
        preset_items = [
            ("Tic-Tac-Toe", "tic_tac_toe"),
            ("Platformer", "platformer"),
            ("Arena", "arena_combat"),
            ("Card battler", "card_battler"),
            ("Explore a world", "procedural_world"),
        ]
        for title, pid in preset_items:
            preset_fn = PRESETS.get(pid)
            prompt_str = ""
            if preset_fn:
                try:
                    spec = preset_fn()
                    prompt_str = spec.meta.source_prompt or spec.overview.pitch
                except Exception:
                    prompt_str = f"Create a {title.lower()} game"
            chip = PresetChip(title, pid, prompt_str, self)
            chip.clicked.connect(self._on_preset_chip_clicked)
            chips_layout.addWidget(chip)
        chips_layout.addStretch(1)
        hero_layout.addLayout(chips_layout)

        # Project Root Location Selection (Two-Location Storage Architecture)
        location_layout = QHBoxLayout()
        location_layout.setSpacing(tokens.SPACE_SM)
        lbl_loc = QLabel("Project Folder:", self)
        lbl_loc.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 500;")
        self._edit_project_dir = QLineEdit(self)
        self._edit_project_dir.setObjectName("homeEditProjectDir")
        self._edit_project_dir.setPlaceholderText("Select user project directory (authoritative root)…")
        self._edit_project_dir.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY}; "
            f"border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; "
            f"padding: 4px 8px; font-size: {tokens.FONT_BODY_SM}px;"
        )
        from src.gameforge_ide.core.settings import get_settings
        s = get_settings()
        default_root = s.projects_root
        if not (default_root and default_root.is_dir()):
            hp_root = s.host_profile.get("projects_root") if hasattr(s, "host_profile") and isinstance(s.host_profile, dict) else None
            if hp_root and Path(hp_root).is_dir():
                default_root = Path(hp_root)
            elif s.artifacts_root and (Path(s.artifacts_root) / "projects").is_dir():
                default_root = Path(s.artifacts_root) / "projects"
            else:
                default_root = Path.home() / "Documents" / "GameForge" / "Projects"
        self._edit_project_dir.setText(str(default_root))
        self._edit_project_dir.textChanged.connect(self._on_project_dir_text_changed)

        btn_browse_loc = QPushButton("Browse…", self)
        btn_browse_loc.setObjectName("homeBtnBrowseProjectDir")
        btn_browse_loc.setCursor(Qt.PointingHandCursor)
        btn_browse_loc.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY}; "
            f"border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px; "
            f"padding: 4px 12px; font-size: {tokens.FONT_BODY_SM}px;"
        )
        btn_browse_loc.clicked.connect(self._on_browse_project_dir_clicked)

        location_layout.addWidget(lbl_loc)
        location_layout.addWidget(self._edit_project_dir, 1)
        location_layout.addWidget(btn_browse_loc)
        hero_layout.addLayout(location_layout)

        # Action Bar: Design it -> + Spinner / Cancel + Unsupported notice
        action_layout = QHBoxLayout()
        action_layout.setSpacing(tokens.SPACE_MD)

        self._btn_design = QPushButton("Design it →", self)
        self._btn_design.setObjectName("homeBtnDesign")
        self._btn_design.setAccessibleName("Design it button")
        self._btn_design.setCursor(Qt.PointingHandCursor)
        self._btn_design.setFixedHeight(34)
        self._btn_design.setStyleSheet(
            f"QPushButton#{self._btn_design.objectName()} {{"
            f"  background-color: {tokens.ACCENT_PRIMARY};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 0 {tokens.SPACE_LG}px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"  font-weight: 600;"
            f"}}"
            f"QPushButton#{self._btn_design.objectName()}:hover {{"
            f"  background-color: {tokens.ACCENT_HOVER};"
            f"}}"
            f"QPushButton#{self._btn_design.objectName()}:pressed {{"
            f"  background-color: {tokens.ACCENT_ACTIVE};"
            f"}}"
            f"QPushButton#{self._btn_design.objectName()}:disabled {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_MUTED};"
            f"}}"
        )
        self._btn_design.clicked.connect(self._on_design_it_clicked)

        self._status_lbl = QLabel("", self)
        self._status_lbl.setObjectName("homeStatusLabel")
        self._status_lbl.setAccessibleName("Design generation status")
        self._status_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")
        self._status_lbl.setVisible(False)

        self._btn_cancel = QPushButton("Cancel", self)
        self._btn_cancel.setObjectName("homeBtnCancel")
        self._btn_cancel.setAccessibleName("Cancel design generation")
        self._btn_cancel.setCursor(Qt.PointingHandCursor)
        self._btn_cancel.setStyleSheet(
            f"QPushButton#{self._btn_cancel.objectName()} {{"
            f"  background: transparent;"
            f"  color: {tokens.ACCENT_ERROR};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton#{self._btn_cancel.objectName()}:hover {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"}}"
        )
        self._btn_cancel.clicked.connect(self._on_cancel_clicked)
        self._btn_cancel.setVisible(False)

        action_layout.addWidget(self._btn_design)
        action_layout.addWidget(self._status_lbl)
        action_layout.addWidget(self._btn_cancel)
        action_layout.addStretch(1)
        hero_layout.addLayout(action_layout)

        # Inline unsupported / error notice
        self._notice_lbl = QLabel(self)
        self._notice_lbl.setObjectName("homeUnsupportedNotice")
        self._notice_lbl.setAccessibleName("Unsupported game request notice")
        self._notice_lbl.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE};"
            f"color: {tokens.ACCENT_WARNING};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"padding: {tokens.SPACE_SM}px {tokens.SPACE_MD}px;"
            f"font-size: {tokens.FONT_BODY_SM}px;"
        )
        self._notice_lbl.setVisible(False)
        hero_layout.addWidget(self._notice_lbl)

        main_layout.addLayout(hero_layout)
        main_layout.addSpacing(tokens.SPACE_MD)

        # ── 2. Bottom Split: Recent Games + Readiness ─────────────────────────
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(tokens.SPACE_LG)

        # Recent Games
        self._recent_section = QFrame(self)
        self._recent_section.setObjectName("homeRecentGamesSection")
        self._recent_section.setAccessibleName("Recent Games Section")
        self._recent_section.setStyleSheet(
            f"QFrame#{self._recent_section.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_MD}px;"
            f"}}"
        )
        recent_vbox = QVBoxLayout(self._recent_section)
        recent_vbox.setContentsMargins(12, 12, 12, 12)
        recent_vbox.setSpacing(tokens.SPACE_SM)

        lbl_recent = QLabel("Recent games", self._recent_section)
        lbl_recent.setObjectName("lblHomeRecentGames")
        lbl_recent.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY};"
            f"font-size: {tokens.FONT_HEADING_SM}px;"
            f"font-weight: 600;"
        )
        recent_vbox.addWidget(lbl_recent)

        self._cards_layout = QHBoxLayout()
        self._cards_layout.setSpacing(tokens.SPACE_MD)
        recent_vbox.addLayout(self._cards_layout)
        recent_vbox.addStretch(1)

        bottom_layout.addWidget(self._recent_section, 3)

        # Readiness
        self._readiness_section = QFrame(self)
        self._readiness_section.setObjectName("homeReadinessSection")
        self._readiness_section.setAccessibleName("Readiness Section")
        self._readiness_section.setStyleSheet(
            f"QFrame#{self._readiness_section.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_MD}px;"
            f"}}"
        )
        readiness_vbox = QVBoxLayout(self._readiness_section)
        readiness_vbox.setContentsMargins(12, 12, 12, 12)
        readiness_vbox.setSpacing(tokens.SPACE_SM)

        lbl_readiness = QLabel("Readiness", self._readiness_section)
        lbl_readiness.setObjectName("lblHomeReadiness")
        lbl_readiness.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY};"
            f"font-size: {tokens.FONT_HEADING_SM}px;"
            f"font-weight: 600;"
        )
        readiness_vbox.addWidget(lbl_readiness)

        self._readiness_rows_layout = QVBoxLayout()
        self._readiness_rows_layout.setSpacing(tokens.SPACE_XS)
        readiness_vbox.addLayout(self._readiness_rows_layout)
        readiness_vbox.addStretch(1)

        bottom_layout.addWidget(self._readiness_section, 2)
        main_layout.addLayout(bottom_layout, 1)

        # Initial data loading
        self.refresh_recent_games()
        self.refresh_readiness()

    # ── Slot helpers ─────────────────────────────────────────────────────────

    @Slot()
    def _on_browse_project_dir_clicked(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        current = self._edit_project_dir.text().strip()
        chosen = QFileDialog.getExistingDirectory(self, "Choose Project Directory", current or str(Path.home()))
        if chosen:
            self._edit_project_dir.setText(str(Path(chosen).resolve()))
            self.refresh_recent_games()

    @Slot(str)
    def _on_project_dir_text_changed(self, text: str) -> None:
        p = Path(text.strip())
        if p.is_dir():
            self.refresh_recent_games()

    @Slot()
    def _on_preset_chip_clicked(self) -> None:
        chip = self.sender()
        if isinstance(chip, PresetChip):
            self._prompt_input.setPlainText(chip.prompt_text)
            self._prompt_input.setFocus()

    @Slot()
    def _on_design_it_clicked(self) -> None:
        prompt_text = self._prompt_input.toPlainText().strip()
        if not prompt_text:
            return

        print(f"[GameForge Studio] Drafting design for prompt: '{prompt_text}'...", flush=True)
        self._notice_lbl.setVisible(False)
        self._btn_design.setEnabled(False)
        self._status_lbl.setText("Drafting a design…")
        self._status_lbl.setVisible(True)
        self._btn_cancel.setVisible(True)

        def work():
            from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds
            from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider
            from src.gameforge_ide.core.settings import get_settings
            from src.gameforge_ide.pipeline.spec_from_prompt import is_game_creation_request

            settings = get_settings()
            provider = OllamaProvider(host=settings.ollama_url.replace("http://", "").replace("https://", ""))
            model = settings.model_for("design")

            def complete_json(system: str, user: str, schema: dict):
                return provider.complete_json(model, system, user, schema)

            effective_prompt = prompt_text
            coding_hints = ("fix", "debug", "error", "bug", "refactor", "compile", "build error", ".cs", ".cpp")
            if not any(k in prompt_text.lower() for k in coding_hints):
                if not is_game_creation_request(effective_prompt):
                    effective_prompt = f"Create a game: {prompt_text}"

            return prompt_to_gds(effective_prompt, complete_json=complete_json, model=model)

        handle = self._job_manager.submit(work, name=f"Draft Design: {prompt_text[:30]}")
        self._active_job = handle
        handle.add_done_callback(self._on_design_job_done)

    def _on_design_job_done(self, handle: JobHandle) -> None:
        # Deliver to UI thread via invokeMethod or direct Qt call if already UI thread
        from PySide6.QtCore import QMetaObject, Qt, Q_ARG
        QMetaObject.invokeMethod(self, "_handle_design_result", Qt.QueuedConnection)

    @Slot()
    def _handle_design_result(self) -> None:
        self._btn_design.setEnabled(True)
        self._status_lbl.setVisible(False)
        self._btn_cancel.setVisible(False)

        if not self._active_job:
            return
        handle = self._active_job
        self._active_job = None

        if handle.status == "CANCELLED":
            self._notice_lbl.setText("Design drafting was cancelled.")
            self._notice_lbl.setVisible(True)
            return

        if handle.status == "FAILED":
            self._notice_lbl.setText(f"Error drafting design: {handle.error}")
            self._notice_lbl.setVisible(True)
            return

        result = handle.result()
        pname = getattr(result.gds.meta, 'project_name', '') if getattr(result, 'gds', None) and hasattr(result.gds, 'meta') else ''
        q_count = len(result.questions) if getattr(result, 'questions', None) else 0

        # Attach authoritative user-selected project directory (Two-Location Storage Architecture)
        pdir_text = self._edit_project_dir.text().strip()
        if pdir_text and getattr(result, "gds", None) and hasattr(result.gds, "meta"):
            base_dir = Path(pdir_text).resolve()
            proj_name = result.gds.meta.project_name or "MyGame"
            if base_dir.name.lower() == proj_name.lower():
                target_pdir = base_dir
            else:
                target_pdir = base_dir / proj_name
            setattr(result.gds.meta, "project_dir", str(target_pdir))

        print(f"[GameForge Studio] Design draft status: {result.status}" + (f" (Project: '{pname}')" if pname else "") + (f" | {q_count} questions" if q_count else ""), flush=True)
        if result.status == "OK":
            self.designReady.emit(result.gds, [])
        elif result.status == "NEEDS_INPUT":
            self.designReady.emit(result.gds, result.questions)
        elif result.status == "UNSUPPORTED":
            self._notice_lbl.setText("That doesn't look like a game request. Try the Assistant.")
            self._notice_lbl.setVisible(True)
            self.openAssistantRequested.emit()
        else:
            err_msg = "; ".join(result.errors) if result.errors else "Unknown design drafting error."
            self._notice_lbl.setText(err_msg)
            self._notice_lbl.setVisible(True)

    @Slot()
    def _on_cancel_clicked(self) -> None:
        if self._active_job:
            self._active_job.cancel()
        self._status_lbl.setText("Cancelling…")
        self._btn_cancel.setEnabled(False)

    def refresh_recent_games(self) -> None:
        """Scan recent games off the UI thread and render cards."""
        pdir = self._edit_project_dir.text().strip() if hasattr(self, "_edit_project_dir") else ""

        def work():
            if pdir and Path(pdir).is_dir():
                custom_games = list_games(projects_root=pdir)
                if custom_games:
                    return custom_games
            return list_games()

        def done(handle: JobHandle):
            if handle.status == "DONE":
                from PySide6.QtCore import QMetaObject, Qt
                res = handle.result()
                self._latest_games = res[:6] if res else []
                QMetaObject.invokeMethod(self, "_render_recent_games", Qt.QueuedConnection)
            else:
                logger.error("Scan Recent Games failed: %s", handle.error)

        handle = self._job_manager.submit(work, name="Scan Recent Games")
        handle.add_done_callback(done)

    @Slot()
    def _render_recent_games(self) -> None:
        # Clear existing cards
        while self._cards_layout.count() > 0:
            item = self._cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        games: List[GameSummary] = getattr(self, "_latest_games", [])
        if not games:
            empty_lbl = QLabel("No recent games yet.", self._recent_section)
            empty_lbl.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_BODY_SM}px;")
            self._cards_layout.addWidget(empty_lbl)
        else:
            for g in games:
                card = RecentGameCard(g, self._recent_section)
                card.clicked.connect(self.projectSelected.emit)
                self._cards_layout.addWidget(card)
        self._cards_layout.addStretch(1)

    def refresh_readiness(self) -> None:
        """Probe system status on JobManager and populate readiness rows."""
        from src.gameforge_ide.core.settings import get_settings

        def work():
            return probe_all(get_settings())

        def done(handle: JobHandle):
            if handle.status == "DONE":
                from PySide6.QtCore import QMetaObject, Qt
                self._latest_snapshot = handle.result()
                QMetaObject.invokeMethod(self, "_render_readiness", Qt.QueuedConnection)

        handle = self._job_manager.submit(work, name="Probe Readiness")
        handle.add_done_callback(done)

    @Slot()
    def _render_readiness(self) -> None:
        while self._readiness_rows_layout.count() > 0:
            item = self._readiness_rows_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        snap: Optional[SystemsSnapshot] = getattr(self, "_latest_snapshot", None)
        if not snap:
            return

        for row in snap.rows:
            rw = ReadinessRowWidget(row, self._readiness_section)
            rw.fixActionRequested.connect(self.fixActionRequested)
            self._readiness_rows_layout.addWidget(rw)
        self._readiness_rows_layout.addStretch(1)

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.refresh_recent_games()
        self.refresh_readiness()

    def attach_systems_service(self, service: SystemsService) -> None:
        """Connect to SystemsService to receive live snapshot updates."""
        def on_snapshot(snap: SystemsSnapshot):
            self._latest_snapshot = snap
            self._render_readiness()
        service.snapshotChanged.connect(on_snapshot)
