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
            'Describe your game… e.g. "a third-person forest adventure where I collect 5 relics while avoiding guards" (Press Ctrl+Enter to design)'
        )
        self.setToolTip("Enter: new line | Ctrl+Enter: Design it")
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
            f"  outline: none;"
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
        self.setToolTip(f"Pre-fill prompt with '{title}' template")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet(
            f"QPushButton#{self.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: 14px;"
            f"  padding: {tokens.SPACE_XS}px {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"  font-weight: 500;"
            f"}}"
            f"QPushButton#{self.objectName()}:hover, QPushButton#{self.objectName()}:focus {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border-color: {tokens.BORDER_FOCUS};"
            f"  outline: none;"
            f"}}"
            f"QPushButton#{self.objectName()}:pressed {{"
            f"  background-color: {tokens.BG_ACTIVE};"
            f"}}"
        )


class RecentGameCard(QFrame):
    """Clickable card displaying a recent game with thumbnail, genre badge, and status."""

    clicked = Signal(str)

    def __init__(self, game: GameSummary, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game = game
        self.setObjectName(f"recentGameCard_{game.name}")
        self.setAccessibleName(f"Recent game {game.title}")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedSize(140, 160)
        self.setStyleSheet(
            f"QFrame#{self.objectName()} {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"}}"
            f"QFrame#{self.objectName()}:hover, QFrame#{self.objectName()}:focus {{"
            f"  border-color: {tokens.BORDER_FOCUS};"
            f"  background-color: {tokens.BG_HOVER};"
            f"  outline: none;"
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(3)

        # Thumbnail
        self._thumb_lbl = QLabel(self)
        self._thumb_lbl.setFixedSize(126, 74)
        self._thumb_lbl.setStyleSheet(
            f"background-color: {tokens.BG_PANEL};"
            f"border-radius: 4px;"
        )
        self._thumb_lbl.setAlignment(Qt.AlignCenter)
        self._load_thumbnail(game.thumbnail_path)
        layout.addWidget(self._thumb_lbl)

        # Title (elided with full text in tooltip)
        title_text = game.title or game.name or "Untitled"
        title_lbl = QLabel(self)
        elided_title = title_lbl.fontMetrics().elidedText(title_text, Qt.ElideRight, 126)
        title_lbl.setText(elided_title)
        title_lbl.setToolTip(title_text)
        title_lbl.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY};"
            f"font-size: {tokens.FONT_BODY}px;"
            f"font-weight: 600;"
        )
        title_lbl.setFixedHeight(18)
        layout.addWidget(title_lbl)

        # Genre badge row
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(tokens.SPACE_XS)

        genre_val = (getattr(game, "genre", "") or "custom").capitalize()
        genre_lbl = QLabel(genre_val, self)
        genre_lbl.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY};"
            f"font-size: {tokens.FONT_BODY_SM}px;"
            f"font-weight: 500;"
        )
        meta_row.addWidget(genre_lbl)
        meta_row.addStretch(1)

        # Status & relative time
        status_text = self._format_status(game)
        status_lbl = QLabel(status_text, self)
        status_lbl.setStyleSheet(
            f"color: {tokens.TEXT_MUTED};"
            f"font-size: {tokens.FONT_BODY_SM}px;"
        )
        meta_row.addWidget(status_lbl)
        layout.addLayout(meta_row)
        layout.addStretch(1)

    def _load_thumbnail(self, path: Optional[Any]) -> None:
        if path and str(path):
            try:
                p = Path(path)
                if p.is_file():
                    pm = QPixmap(str(p))
                    if not pm.isNull():
                        scaled = pm.scaled(126, 78, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self._thumb_lbl.setPixmap(scaled)
                        return
            except Exception:
                pass
        # Placeholder
        self._thumb_lbl.setText("🎮")

    def _format_status(self, game: GameSummary) -> str:
        status_part = game.last_run_status or "—"
        if status_part in ("DONE", "PASS"):
            status_part = "PASS"
        elif status_part in ("FAILED", "FAIL"):
            status_part = "FAIL"
        time_part = ""
        up_at = getattr(game, "updated_at", 0.0) or 0.0
        if up_at > 0:
            diff_s = max(0.0, time.time() - up_at)
            if diff_s < 3600:
                time_part = f"{int(diff_s // 60)}m"
            elif diff_s < 86400:
                time_part = f"{int(diff_s // 3600)}h"
            else:
                time_part = f"{int(diff_s // 86400)}d"
        return f"{status_part} {time_part}".strip()

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.LeftButton:
            if self.game and getattr(self.game, "name", None):
                self.clicked.emit(self.game.name)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        if event.button() == Qt.LeftButton:
            if self.game and getattr(self.game, "name", None):
                self.clicked.emit(self.game.name)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if self.game and getattr(self.game, "name", None):
                self.clicked.emit(self.game.name)
            event.accept()
            return
        super().keyPressEvent(event)


class ReadinessRowWidget(QWidget):
    """Row displaying a single readiness probe outcome."""

    fixActionRequested = Signal(str)

    def __init__(self, row: SystemRow, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(f"readinessRow_{row.key}")
        self.setAccessibleName(f"Readiness item {row.key}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(tokens.SPACE_SM)

        # Status indicator: prominent badge and dot
        is_ok = row.state == "ok"
        is_deg = row.state == "degraded"
        status_color = tokens.ACCENT_SUCCESS if is_ok else (
            tokens.ACCENT_WARNING if is_deg else tokens.ACCENT_ERROR
        )
        status_text = "READY" if is_ok else ("DEGRADED" if is_deg else "OFFLINE")

        badge_lbl = QLabel(f"● {status_text}", self)
        badge_lbl.setStyleSheet(
            f"color: {status_color}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 700;"
        )
        badge_lbl.setFixedWidth(74)
        layout.addWidget(badge_lbl)

        # Key title + summary
        r_key = str(getattr(row, "key", "") or "")
        r_summary = str(getattr(row, "summary", "") or "Unknown")
        label_text = f"{r_key.capitalize()}: {r_summary}"
        if r_key == "engine":
            label_text = f"Unreal Engine {r_summary}"
        elif r_key == "ollama":
            label_text = f"Ollama · {r_summary}"
        elif r_key == "disk":
            label_text = f"Disk {r_summary}"
        elif r_key == "hosted":
            label_text = f"Hosted models: {r_summary}"

        text_lbl = QLabel(label_text, self)
        text_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        layout.addWidget(text_lbl, 1)

        if row.fix_action:
            btn = QPushButton("Set up", self)
            btn.setObjectName(f"btn_fix_{row.key}")
            btn.setAccessibleName(f"Set up {row.key.capitalize()}")
            btn.setCursor(Qt.PointingHandCursor)
            action_key = str(row.fix_action)
            btn.clicked.connect(lambda checked=False, act=action_key: self.fixActionRequested.emit(act))
            btn.setToolTip(f"Set up {row.key.capitalize()}")
            btn.setStyleSheet(
                f"QPushButton#{btn.objectName()} {{"
                f"  background-color: {tokens.BG_SURFACE};"
                f"  color: {tokens.ACCENT_HOVER};"
                f"  border: 1px solid {tokens.BORDER};"
                f"  border-radius: {tokens.RADIUS}px;"
                f"  padding: 2px {tokens.SPACE_SM}px;"
                f"  font-size: {tokens.FONT_BODY_SM}px;"
                f"  font-weight: 600;"
                f"}}"
                f"QPushButton#{btn.objectName()}:hover, QPushButton#{btn.objectName()}:focus {{"
                f"  background-color: {tokens.BG_HOVER};"
                f"  border-color: {tokens.BORDER_FOCUS};"
                f"  color: {tokens.TEXT_PRIMARY};"
                f"  outline: none;"
                f"}}"
            )
            layout.addWidget(btn)


class HomeView(QWidget):
    """Home view implementation for Studio UX."""

    designReady = Signal(object, list)       # (GameDesignSpec, questions)
    projectSelected = Signal(str)             # (project_name)
    projectDirectoryChangeRequested = Signal(Path)  # (Path) -> Authoritative directory update
    openAssistantRequested = Signal()         # Request to open assistant panel
    fixActionRequested = Signal(str)          # ("start_ollama" | "set_engine" | "open_hosted")

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("homeView")
        self.setAccessibleName("GameForge Home View")

        self._active_job: Optional[JobHandle] = None
        self._job_manager = default_job_manager()
        self._scan_generation: int = 0
        self._projects_service: Optional[Any] = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 28, 32, 28)
        main_layout.setSpacing(tokens.SPACE_MD)

        # ── 1. Dashboard Header ──────────────────────────────────────────────
        dash_header = QVBoxLayout()
        dash_header.setSpacing(4)

        title_lbl = QLabel("Studio Dashboard", self)
        title_lbl.setObjectName("homeTitle")
        title_lbl.setAccessibleName("Dashboard title")
        title_lbl.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY};"
            f"font-size: {tokens.FONT_HEADING}px;"
            f"font-weight: 700;"
        )
        dash_header.addWidget(title_lbl)

        sub_lbl = QLabel("System readiness and project overview. All code creation, game generation, and modifications flow through the Assistant chat on the right.", self)
        sub_lbl.setObjectName("homeSubtitle")
        sub_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")
        dash_header.addWidget(sub_lbl)
        main_layout.addLayout(dash_header)
        main_layout.addSpacing(tokens.SPACE_MD)

        # Internal widgets retained hidden for backward compatibility and test stability
        self._prompt_input = PromptTextEdit(self)
        self._prompt_input.setVisible(False)
        self._btn_design = QPushButton("Design it →", self)
        self._btn_design.setObjectName("homeBtnDesign")
        self._btn_design.setVisible(False)
        self._btn_cancel = QPushButton("Cancel", self)
        self._btn_cancel.setObjectName("homeBtnCancel")
        self._btn_cancel.setVisible(False)
        self._status_lbl = QLabel("", self)
        self._status_lbl.setObjectName("homeStatusLabel")
        self._status_lbl.setVisible(False)
        self._notice_lbl = QLabel("", self)
        self._notice_lbl.setObjectName("homeUnsupportedNotice")
        self._notice_lbl.setVisible(False)

        self._preset_chips: Dict[str, PresetChip] = {}
        preset_items = [
            ("Tic-Tac-Toe", "tic_tac_toe"),
            ("Platformer", "platformer"),
            ("Arena", "arena_combat"),
            ("Card battler", "card_battler"),
            ("Explore a world", "procedural_world"),
        ]
        for title, pid in preset_items:
            preset_fn = PRESETS.get(pid)
            prompt_str = f"Create a {title.lower()} game"
            if preset_fn:
                try:
                    spec = preset_fn()
                    prompt_str = spec.meta.source_prompt or spec.overview.pitch
                except Exception:
                    pass
            chip = PresetChip(title, pid, prompt_str, self)
            chip.setVisible(False)
            chip.clicked.connect(self._on_preset_chip_clicked)
            self._preset_chips[pid] = chip

        # Internal project directory reference (authoritative root managed centrally via TopBar and Settings)
        self._edit_project_dir = QLineEdit(self)
        self._edit_project_dir.setObjectName("homeEditProjectDir")
        self._edit_project_dir.setVisible(False)
        from src.gameforge_ide.core.settings import get_settings
        s = get_settings()
        default_root = s.projects_root
        if not default_root:
            hp_root = s.host_profile.get("projects_root") if hasattr(s, "host_profile") and isinstance(s.host_profile, dict) else None
            if hp_root:
                default_root = Path(hp_root)
            elif s.artifacts_root:
                default_root = Path(s.artifacts_root) / "projects"
            else:
                default_root = Path.home() / "Documents" / "GameForge" / "Projects"
        self._edit_project_dir.setText(str(default_root))
        self._edit_project_dir.textChanged.connect(self._on_project_dir_text_changed)

        # ── 2. Primary Dashboard: Readiness (Game catalog is consolidated in Games View) ──
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(tokens.SPACE_LG)

        # Recent Games section on HomeView
        self._recent_section = QFrame(self)
        self._recent_section.setObjectName("homeRecentGamesSection")
        self._recent_section.setAccessibleName("Recent Games Section")
        self._recent_section.setVisible(True)
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

        # Readiness (Expanded across full dashboard width on Home)
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

        bottom_layout.addWidget(self._recent_section, 1)
        bottom_layout.addWidget(self._readiness_section, 1)
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
            pdir = Path(chosen).resolve()
            self._edit_project_dir.setText(str(pdir))
            self.projectDirectoryChangeRequested.emit(pdir)
            self.refresh_recent_games()

    @Slot(str)
    def _on_project_dir_text_changed(self, text: str) -> None:
        try:
            p = Path(text.strip())
            if p.is_dir():
                resolved = p.resolve()
                if hasattr(self, "_projects_service") and self._projects_service is not None:
                    if hasattr(self._projects_service, "_projects_root"):
                        from src.gameforge_ide.core.projects import is_gameforge_project
                        p_root = resolved.parent if is_gameforge_project(resolved) else resolved
                        self._projects_service._projects_root = p_root
                self.projectDirectoryChangeRequested.emit(resolved)
                self.refresh_recent_games()
        except Exception:
            pass

    @Slot()
    def _on_preset_chip_clicked(self) -> None:
        chip = self.sender()
        if isinstance(chip, PresetChip):
            self._prompt_input.setPlainText(chip.prompt_text)
            self._prompt_input.setFocus()

    @Slot()
    def _on_design_it_clicked(self) -> None:
        if self._active_job and not self._active_job.done:
            return
        prompt_text = self._prompt_input.toPlainText().strip()
        if not prompt_text:
            return

        print(f"[GameForge Studio] Drafting design for prompt: '{prompt_text}'...", flush=True)
        self._notice_lbl.setVisible(False)
        self._btn_design.setEnabled(False)
        self._status_lbl.setText("⏳ Drafting design spec with Ollama…")
        self._status_lbl.setVisible(True)
        self._btn_cancel.setVisible(True)
        self._btn_cancel.setEnabled(True)

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
        try:
            import shiboken6
            if not shiboken6.isValid(self):
                return
        except Exception:
            pass
        try:
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self, "_handle_design_result", Qt.QueuedConnection)
        except Exception:
            pass

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

        try:
            result = handle.result()
        except Exception as exc:
            self._notice_lbl.setText(f"Error drafting design: {exc}")
            self._notice_lbl.setVisible(True)
            return

        if not result:
            self._notice_lbl.setText("Design drafting failed: no result returned.")
            self._notice_lbl.setVisible(True)
            return

        gds = getattr(result, "gds", None)
        pname = getattr(gds.meta, 'project_name', '') if gds and hasattr(gds, 'meta') else ''
        q_count = len(result.questions) if getattr(result, 'questions', None) else 0

        # Attach authoritative user-selected project directory (Two-Location Storage Architecture)
        pdir_text = self._edit_project_dir.text().strip()
        if pdir_text and gds and hasattr(gds, "meta"):
            try:
                base_dir = Path(pdir_text).resolve()
                proj_name = getattr(gds.meta, "project_name", None) or "MyGame"
                if base_dir.name.lower() == proj_name.lower():
                    target_pdir = base_dir
                else:
                    from src.gameforge_ide.core.settings import get_settings
                    s_root = get_settings().projects_root
                    if s_root and (base_dir == Path(s_root).resolve() or base_dir.parent == Path(s_root).resolve()):
                        target_pdir = Path(s_root).resolve() / proj_name
                    elif (base_dir / "GameForge").is_dir() or any(base_dir.glob("*.uproject")):
                        target_pdir = base_dir.parent / proj_name
                    else:
                        target_pdir = base_dir / proj_name
                setattr(gds.meta, "project_dir", str(target_pdir))
            except Exception as e:
                logger.warning("Could not resolve project directory '%s': %s", pdir_text, e)

        print(f"[GameForge Studio] Design draft status: {result.status}" + (f" (Project: '{pname}')" if pname else "") + (f" | {q_count} questions" if q_count else ""), flush=True)
        if result.status == "OK":
            if gds:
                self.designReady.emit(gds, [])
            else:
                self._notice_lbl.setText("Design generated without a valid specification.")
                self._notice_lbl.setVisible(True)
        elif result.status == "NEEDS_INPUT":
            if gds:
                self.designReady.emit(gds, result.questions or [])
            else:
                # Model transport error or clarification required before GDS can be built
                q_text = "\n".join(result.questions) if getattr(result, "questions", None) else ""
                err_text = "; ".join(result.errors) if getattr(result, "errors", None) else ""
                msg = q_text or err_text or "Could not generate design spec. Please ensure Ollama is running and try again."
                self._notice_lbl.setText(msg)
                self._notice_lbl.setVisible(True)
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

    def attach_projects_service(self, service: Any) -> None:
        """Connect to shared ProjectsService to consume project updates."""
        self._projects_service = service
        if hasattr(service, "gamesLoaded"):
            service.gamesLoaded.connect(self._on_projects_loaded)
        if hasattr(service, "gameDeleted"):
            service.gameDeleted.connect(lambda _: self.refresh_recent_games())

    @Slot(list)
    def _on_projects_loaded(self, games: List[GameSummary]) -> None:
        self._latest_games = games[:6] if games else []
        from PySide6.QtCore import QMetaObject, Qt
        QMetaObject.invokeMethod(self, "_render_recent_games", Qt.QueuedConnection)

    def set_project_directory(self, path: Path | str) -> None:
        """Programmatically update authoritative project directory and refresh games."""
        try:
            resolved = Path(path).resolve()
        except Exception:
            resolved = Path(path)
        if hasattr(self, "_edit_project_dir"):
            self._edit_project_dir.setText(str(resolved))
        if hasattr(self, "_projects_service") and self._projects_service is not None:
            if hasattr(self._projects_service, "_projects_root"):
                # If path is an individual game project, the projects root is its parent directory
                from src.gameforge_ide.core.projects import is_gameforge_project
                p_root = resolved.parent if is_gameforge_project(resolved) else resolved
                self._projects_service._projects_root = p_root
        self.refresh_recent_games()

    def refresh_recent_games(self) -> None:
        """Scan recent games off the UI thread and render cards."""
        self._scan_generation += 1
        current_gen = self._scan_generation
        pdir = self._edit_project_dir.text().strip() if hasattr(self, "_edit_project_dir") else ""

        if hasattr(self, "_projects_service") and self._projects_service is not None:
            if hasattr(self._projects_service, "refresh"):
                self._projects_service.refresh()
                return

        def work():
            if pdir and Path(pdir).is_dir():
                return list_games(projects_root=pdir)
            return list_games()

        def done(handle: JobHandle):
            if current_gen != self._scan_generation:
                return
            try:
                import shiboken6
                if not shiboken6.isValid(self):
                    return
            except Exception:
                pass
            from PySide6.QtCore import QMetaObject, Qt
            if handle.status == "DONE":
                res = handle.result()
                self._latest_games = res[:6] if res else []
            else:
                logger.error("Scan Recent Games failed: %s", handle.error)
                self._latest_games = []
            try:
                QMetaObject.invokeMethod(self, "_render_recent_games", Qt.QueuedConnection)
            except Exception:
                pass

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
            empty_frame = QFrame(self._recent_section)
            empty_frame.setObjectName("homeRecentGamesEmpty")
            empty_frame.setStyleSheet(
                f"QFrame#{empty_frame.objectName()} {{"
                f"  background-color: {tokens.BG_SURFACE};"
                f"  border: 1px dashed {tokens.BORDER};"
                f"  border-radius: {tokens.RADIUS}px;"
                f"  padding: {tokens.SPACE_MD}px;"
                f"}}"
            )
            empty_box = QVBoxLayout(empty_frame)
            empty_box.setContentsMargins(12, 10, 12, 10)
            empty_box.setSpacing(4)
            empty_lbl = QLabel("No recent games yet.", empty_frame)
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY}px; font-weight: 600;")
            empty_sub = QLabel("Type a prompt above or pick a preset chip to create your first game.", empty_frame)
            empty_sub.setAlignment(Qt.AlignCenter)
            empty_sub.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_BODY_SM}px;")
            empty_box.addWidget(empty_lbl)
            empty_box.addWidget(empty_sub)
            self._cards_layout.addWidget(empty_frame)
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
            try:
                import shiboken6
                if not shiboken6.isValid(self):
                    return
            except Exception:
                pass
            from PySide6.QtCore import QMetaObject, Qt
            if handle.status == "DONE":
                self._latest_snapshot = handle.result()
            else:
                logger.error("Readiness probe failed: %s", handle.error)
                self._latest_snapshot = None
            try:
                QMetaObject.invokeMethod(self, "_render_readiness", Qt.QueuedConnection)
            except Exception:
                pass

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
        if not snap or not getattr(snap, "rows", None):
            lbl = QLabel("System status unavailable or probing failed.", self._readiness_section)
            lbl.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_BODY_SM}px;")
            self._readiness_rows_layout.addWidget(lbl)
            self._readiness_rows_layout.addStretch(1)
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
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self, "_render_readiness", Qt.QueuedConnection)

        self._systems_snapshot_slot = on_snapshot
        service.snapshotChanged.connect(on_snapshot)
