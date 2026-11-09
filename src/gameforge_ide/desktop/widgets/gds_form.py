"""GDS Form: section-by-section form with explicit widgets and debounced validation (spec §4.3, WI-4.6)."""
from __future__ import annotations

import copy
import logging
import re
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from .rule_editor import RuleEditorDialog
from ...design.gds import (
    CameraKind,
    Condition,
    CountAtLeast,
    EndGame,
    EntityKind,
    EntitySpec,
    GameDesignSpec,
    Genre,
    LevelSpec,
    RuleSpec,
)
from ...design.render import sentence

logger = logging.getLogger(__name__)


class CollapsibleSection(QFrame):
    """Collapsible card container for secondary GDS sections."""

    def __init__(
        self,
        title: str,
        parent: Optional[QWidget] = None,
        object_name: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        safe_name = object_name or re.sub(r"[^a-zA-Z0-9_]", "", f"collapsible_{title.replace(' ', '_').lower()}")
        self.setObjectName(safe_name)
        self.setAccessibleName(f"{title} collapsible section")
        self.setAccessibleDescription("Collapsed")
        self.setStyleSheet(
            f"QFrame#{safe_name} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Header bar
        header = QHBoxLayout()
        self._toggle_btn = QPushButton(f"▶  {title}", self)
        self._toggle_btn.setObjectName(f"btn_toggle_{safe_name}")
        self._toggle_btn.setAccessibleName(f"Toggle {title} section")
        self._toggle_btn.setFocusPolicy(Qt.StrongFocus)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent;"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"  font-weight: 600;"
            f"  text-align: left;"
            f"  padding: 2px 4px;"
            f"}}"
            f"QPushButton:hover {{ color: {tokens.ACCENT_HOVER}; }}"
            f"QPushButton:focus {{ outline: 1px solid {tokens.BORDER_FOCUS}; border-radius: {tokens.RADIUS}px; }}"
        )
        self._toggle_btn.clicked.connect(self._toggle)
        header.addWidget(self._toggle_btn)
        header.addStretch(1)
        layout.addLayout(header)

        # Body container
        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 4, 0, 4)
        self._body.setVisible(False)
        layout.addWidget(self._body)

        self._title = title

    def add_widget(self, w: QWidget) -> None:
        self._body_layout.addWidget(w)

    def _toggle(self) -> None:
        vis = not self._body.isVisible()
        self._body.setVisible(vis)
        arrow = "▼" if vis else "▶"
        self._toggle_btn.setText(f"{arrow}  {self._title}")
        self.setAccessibleDescription("Expanded" if vis else "Collapsed")


class GdsForm(QWidget):
    """Form for viewing and editing a GameDesignSpec with debounced validation."""

    changed = Signal()
    validationChanged = Signal(bool, list)  # (is_valid, error_messages)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("gdsForm")
        self.setAccessibleName("Game Design Spec Form")

        self._spec: Optional[GameDesignSpec] = None
        self._is_populating: bool = False

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._validate_form)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(tokens.SPACE_LG)

        # ── 1. Overview Section (Two-Column Grid) ─────────────────────────────
        sec_overview = self._create_card("Overview", "cardOverview")
        olayout = QVBoxLayout(sec_overview)
        olayout.setContentsMargins(14, 14, 14, 14)
        olayout.setSpacing(tokens.SPACE_MD)

        grid_overview = QHBoxLayout()
        grid_overview.setSpacing(tokens.SPACE_LG)

        # Left Column: Title, Genre, Camera, Session & Players
        col_left = QVBoxLayout()
        col_left.setSpacing(tokens.SPACE_SM)

        # Title
        vbox_title = QVBoxLayout()
        vbox_title.setSpacing(tokens.SPACE_XS)
        lbl_title = QLabel("Game Title:", sec_overview)
        lbl_title.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600;")
        self._edit_title = QLineEdit(sec_overview)
        self._edit_title.setObjectName("gdsTitleInput")
        self._edit_title.setAccessibleName("Game Title")
        self._edit_title.setPlaceholderText("Untitled Game")
        self._edit_title.textChanged.connect(self._on_field_changed)
        self._style_input(self._edit_title)
        vbox_title.addWidget(lbl_title)
        vbox_title.addWidget(self._edit_title)
        col_left.addLayout(vbox_title)

        # Genre & Camera row
        row_gc = QHBoxLayout()
        row_gc.setSpacing(tokens.SPACE_MD)

        vbox_genre = QVBoxLayout()
        vbox_genre.setSpacing(tokens.SPACE_XS)
        lbl_genre = QLabel("Genre:", sec_overview)
        lbl_genre.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._combo_genre = QComboBox(sec_overview)
        self._combo_genre.setObjectName("gdsGenreCombo")
        self._combo_genre.setAccessibleName("Game Genre")
        for g in Genre:
            self._combo_genre.addItem(g.value.capitalize(), userData=g.value)
        self._combo_genre.currentIndexChanged.connect(self._on_field_changed)
        self._style_input(self._combo_genre)
        vbox_genre.addWidget(lbl_genre)
        vbox_genre.addWidget(self._combo_genre)
        row_gc.addLayout(vbox_genre, 1)

        vbox_cam = QVBoxLayout()
        vbox_cam.setSpacing(tokens.SPACE_XS)
        lbl_cam = QLabel("Camera:", sec_overview)
        lbl_cam.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._combo_camera = QComboBox(sec_overview)
        self._combo_camera.setObjectName("gdsCameraCombo")
        self._combo_camera.setAccessibleName("Camera Style")
        for c in CameraKind:
            self._combo_camera.addItem(c.value.replace("_", " ").capitalize(), userData=c.value)
        self._combo_camera.currentIndexChanged.connect(self._on_field_changed)
        self._style_input(self._combo_camera)
        vbox_cam.addWidget(lbl_cam)
        vbox_cam.addWidget(self._combo_camera)
        row_gc.addLayout(vbox_cam, 1)
        col_left.addLayout(row_gc)

        # Session & Players row
        row_sp = QHBoxLayout()
        row_sp.setSpacing(tokens.SPACE_MD)

        vbox_session = QVBoxLayout()
        vbox_session.setSpacing(tokens.SPACE_XS)
        lbl_session = QLabel("Target Session (min):", sec_overview)
        lbl_session.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._spin_session = QSpinBox(sec_overview)
        self._spin_session.setObjectName("gdsSessionSpin")
        self._spin_session.setAccessibleName("Target Session Duration in Minutes")
        self._spin_session.setRange(1, 180)
        self._spin_session.setValue(10)
        self._spin_session.valueChanged.connect(self._on_field_changed)
        self._style_input(self._spin_session)
        vbox_session.addWidget(lbl_session)
        vbox_session.addWidget(self._spin_session)
        row_sp.addLayout(vbox_session, 1)

        vbox_players = QVBoxLayout()
        vbox_players.setSpacing(tokens.SPACE_XS)
        lbl_players = QLabel("Players:", sec_overview)
        lbl_players.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._spin_players = QSpinBox(sec_overview)
        self._spin_players.setObjectName("gdsPlayersSpin")
        self._spin_players.setAccessibleName("Number of Players")
        self._spin_players.setRange(1, 8)
        self._spin_players.setValue(1)
        self._spin_players.valueChanged.connect(self._on_field_changed)
        self._style_input(self._spin_players)
        vbox_players.addWidget(lbl_players)
        vbox_players.addWidget(self._spin_players)
        row_sp.addLayout(vbox_players, 1)
        col_left.addLayout(row_sp)

        grid_overview.addLayout(col_left, 1)

        # Right Column: Pitch / Core Concept
        col_right = QVBoxLayout()
        col_right.setSpacing(tokens.SPACE_XS)
        lbl_pitch = QLabel("Pitch / Game Concept:", sec_overview)
        lbl_pitch.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600;")
        self._edit_pitch = QPlainTextEdit(sec_overview)
        self._edit_pitch.setObjectName("gdsPitchInput")
        self._edit_pitch.setAccessibleName("Elevator Pitch and Game Concept")
        self._edit_pitch.setPlaceholderText("Brief elevator pitch for the core game mechanics, player goal, tone, and loop...")
        self._edit_pitch.textChanged.connect(self._on_field_changed)
        self._style_input(self._edit_pitch)
        col_right.addWidget(lbl_pitch)
        col_right.addWidget(self._edit_pitch, 1)

        grid_overview.addLayout(col_right, 1)
        olayout.addLayout(grid_overview)

        main_layout.addWidget(sec_overview)

        # ── 2. World / Levels Section ─────────────────────────────────────────
        sec_world = self._create_card("World (Levels)", "cardWorld")
        wlayout = QVBoxLayout(sec_world)
        wlayout.setContentsMargins(14, 14, 14, 14)
        wlayout.setSpacing(tokens.SPACE_MD)

        self._table_levels = QTableWidget(sec_world)
        self._table_levels.setObjectName("gdsLevelsTable")
        self._table_levels.setColumnCount(4)
        self._table_levels.setHorizontalHeaderLabels(["Level ID", "Layout", "Size (m)", "Lighting"])
        self._table_levels.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table_levels.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table_levels.setSelectionBehavior(QTableWidget.SelectRows)
        self._table_levels.setFixedHeight(120)
        self._table_levels.setStyleSheet(
            f"QTableWidget {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"}}"
        )
        wlayout.addWidget(self._table_levels)
        main_layout.addWidget(sec_world)

        # ── 3. Things / Entities Section ──────────────────────────────────────
        sec_things = self._create_card("Things in the Game (Entities)", "cardThings")
        tlayout = QVBoxLayout(sec_things)
        tlayout.setContentsMargins(14, 14, 14, 14)
        tlayout.setSpacing(tokens.SPACE_MD)

        self._table_entities = QTableWidget(sec_things)
        self._table_entities.setObjectName("gdsEntitiesTable")
        self._table_entities.setColumnCount(5)
        self._table_entities.setHorizontalHeaderLabels(["Entity ID", "Kind", "Count", "Module", "Placement"])
        self._table_entities.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table_entities.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table_entities.setSelectionBehavior(QTableWidget.SelectRows)
        self._table_entities.setFixedHeight(160)
        self._table_entities.setStyleSheet(
            f"QTableWidget {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"}}"
        )
        tlayout.addWidget(self._table_entities)
        main_layout.addWidget(sec_things)

        # ── 4. Rules & Goals Section ──────────────────────────────────────────
        sec_rules = self._create_card("Rules & Goals", "cardRules")
        rlayout = QVBoxLayout(sec_rules)
        rlayout.setContentsMargins(14, 14, 14, 14)
        rlayout.setSpacing(tokens.SPACE_MD)

        lbl_rules_sub = QLabel("Game Rules (Sentence view):", sec_rules)
        lbl_rules_sub.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        rlayout.addWidget(lbl_rules_sub)

        self._table_rules = QTableWidget(sec_rules)
        self._table_rules.setObjectName("gdsRulesTable")
        self._table_rules.setColumnCount(2)
        self._table_rules.setHorizontalHeaderLabels(["Rule Description / Sentence", "Action"])
        self._table_rules.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table_rules.setColumnWidth(1, 90)
        self._table_rules.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table_rules.setSelectionBehavior(QTableWidget.SelectRows)
        self._table_rules.setFixedHeight(120)
        self._table_rules.setStyleSheet(
            f"QTableWidget {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"}}"
        )
        rlayout.addWidget(self._table_rules)

        btn_add_rule = QPushButton("+ Add Rule", sec_rules)
        btn_add_rule.setObjectName("gdsBtnAddRule")
        btn_add_rule.setCursor(Qt.PointingHandCursor)
        btn_add_rule.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 4px {tokens.SPACE_MD}px;"
            f"  font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        btn_add_rule.clicked.connect(self._on_add_rule_clicked)
        rlayout.addWidget(btn_add_rule)

        # Goals: Win & Lose sentences
        goals_box = QHBoxLayout()
        goals_box.setSpacing(tokens.SPACE_MD)

        vbox_win = QVBoxLayout()
        lbl_win = QLabel("Win Conditions:", sec_rules)
        lbl_win.setStyleSheet(f"color: {tokens.ACCENT_SUCCESS}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600;")
        self._edit_win = QLineEdit(sec_rules)
        self._edit_win.setObjectName("gdsWinInput")
        self._style_input(self._edit_win)
        self._edit_win.textChanged.connect(self._on_field_changed)
        vbox_win.addWidget(lbl_win)
        vbox_win.addWidget(self._edit_win)
        goals_box.addLayout(vbox_win)

        vbox_lose = QVBoxLayout()
        lbl_lose = QLabel("Lose Conditions:", sec_rules)
        lbl_lose.setStyleSheet(f"color: {tokens.ACCENT_ERROR}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600;")
        self._edit_lose = QLineEdit(sec_rules)
        self._edit_lose.setObjectName("gdsLoseInput")
        self._style_input(self._edit_lose)
        self._edit_lose.textChanged.connect(self._on_field_changed)
        vbox_lose.addWidget(lbl_lose)
        vbox_lose.addWidget(self._edit_lose)
        goals_box.addLayout(vbox_lose)

        rlayout.addLayout(goals_box)
        main_layout.addWidget(sec_rules)

        # ── 5. Collapsible Sections ───────────────────────────────────────────
        self._sec_look_sound = CollapsibleSection("Look & Sound", self, object_name="secLookSound")
        self._lbl_look = QLabel("Art style: Low-poly stylized | Audio: Procedural SFX & Ambient music", self._sec_look_sound)
        self._lbl_look.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._sec_look_sound.add_widget(self._lbl_look)
        main_layout.addWidget(self._sec_look_sound)

        self._sec_hud_menus = CollapsibleSection("HUD & Menus", self, object_name="secHudMenus")
        self._lbl_hud = QLabel("HUD: Reticle, Score, Health bar | Menus: Pause, Game Over screen", self._sec_hud_menus)
        self._lbl_hud.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._sec_hud_menus.add_widget(self._lbl_hud)
        main_layout.addWidget(self._sec_hud_menus)

        self._sec_tech = CollapsibleSection("Tech & Budgets", self, object_name="secTech")
        self._lbl_tech = QLabel("Target: 60 FPS Win64 | Max draw calls: 1500 | Memory budget: 4 GB", self._sec_tech)
        self._lbl_tech.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._sec_tech.add_widget(self._lbl_tech)
        main_layout.addWidget(self._sec_tech)

        self._sec_acceptance = CollapsibleSection("Acceptance Tests (Scenarios)", self, object_name="secAcceptance")
        self._lbl_scenarios = QLabel("No scenarios generated yet.", self._sec_acceptance)
        self._lbl_scenarios.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._sec_acceptance.add_widget(self._lbl_scenarios)
        main_layout.addWidget(self._sec_acceptance)

    def _create_card(self, title: str, obj_name: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName(obj_name)
        card.setStyleSheet(
            f"QFrame#{obj_name} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"}}"
        )
        return card

    def _style_input(self, widget: QWidget) -> None:
        widget.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE};"
            f"color: {tokens.TEXT_PRIMARY};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"padding: 4px {tokens.SPACE_SM}px;"
            f"font-size: {tokens.FONT_BODY}px;"
        )

    def set_spec(self, spec: Optional[GameDesignSpec]) -> None:
        """Populate form with GameDesignSpec data."""
        if spec is None:
            self._spec = None
            if hasattr(self, "_edit_title"):
                self._edit_title.clear()
            self._combo_genre.setCurrentIndex(0)
            self._combo_camera.setCurrentIndex(0)
            self._spin_session.setValue(10)
            self._spin_players.setValue(1)
            self._edit_pitch.clear()
            self._table_levels.setRowCount(0)
            self._table_entities.setRowCount(0)
            self._table_rules.setRowCount(0)
            self._edit_win.clear()
            self._edit_lose.clear()
            return

        self._spec = copy.deepcopy(spec)
        self._is_populating = True
        try:
            # Overview Title
            if hasattr(self, "_edit_title"):
                t_val = spec.meta.title if (spec.meta and spec.meta.title) else ""
                self._edit_title.setText(t_val)

            # Overview Parameters
            genre_val = spec.overview.genre.value if hasattr(spec.overview.genre, "value") else str(spec.overview.genre)
            idx = self._combo_genre.findData(genre_val)
            if idx >= 0:
                self._combo_genre.setCurrentIndex(idx)

            cam_val = spec.overview.camera.value if hasattr(spec.overview.camera, "value") else str(spec.overview.camera)
            idx = self._combo_camera.findData(cam_val)
            if idx >= 0:
                self._combo_camera.setCurrentIndex(idx)

            self._spin_session.setValue(spec.overview.session_minutes or 10)
            self._spin_players.setValue(spec.overview.players or 1)
            self._edit_pitch.setPlainText(spec.overview.pitch or "")

            # Levels
            self._table_levels.setRowCount(len(spec.scene.levels))
            for r, lvl in enumerate(spec.scene.levels):
                for col_idx, text_val in enumerate([
                    lvl.level_id,
                    lvl.layout.value if hasattr(lvl.layout, "value") else str(lvl.layout),
                    f"{lvl.size_m.x}x{lvl.size_m.y}" if lvl.size_m else "—",
                    lvl.lighting.value if hasattr(lvl.lighting, "value") else str(lvl.lighting or "day"),
                ]):
                    it = QTableWidgetItem(text_val)
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    self._table_levels.setItem(r, col_idx, it)

            # Entities
            self._table_entities.setRowCount(len(spec.entities))
            for r, ent in enumerate(spec.entities):
                kind_str = ent.kind.value if hasattr(ent.kind, "value") else str(ent.kind)
                plc = ent.placement.strategy if ent.placement else "default"
                for col_idx, text_val in enumerate([
                    ent.entity_id,
                    kind_str,
                    str(ent.count),
                    ent.module or "kit",
                    str(plc),
                ]):
                    it = QTableWidgetItem(text_val)
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    self._table_entities.setItem(r, col_idx, it)

            # Rules
            self._table_rules.setRowCount(len(spec.rules))
            for r, rule in enumerate(spec.rules):
                try:
                    s_text = sentence(rule) if rule else ""
                except Exception:
                    s_text = str(getattr(rule, "description", getattr(rule, "rule_id", "rule")))
                it_rule = QTableWidgetItem(s_text)
                it_rule.setFlags(it_rule.flags() & ~Qt.ItemIsEditable)
                self._table_rules.setItem(r, 0, it_rule)
                btn_edit = QPushButton("Edit", self._table_rules)
                btn_edit.setStyleSheet(
                    f"background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
                    f"border: 1px solid {tokens.BORDER}; border-radius: 4px; padding: 2px 6px;"
                )
                btn_edit.clicked.connect(lambda _, row=r: self._on_edit_rule_clicked(row))
                self._table_rules.setCellWidget(r, 1, btn_edit)

            # Goals
            win_texts = [self._format_condition(c) for c in spec.goals.win]
            lose_texts = [self._format_condition(c) for c in spec.goals.lose]
            self._edit_win.setText(", ".join(win_texts) if win_texts else "entity.relics.collected >= 5")
            self._edit_lose.setText(", ".join(lose_texts) if lose_texts else "player.health <= 0")

            # Look & Sound / HUD / Tech dynamic updates
            look_obj = getattr(spec, "look_and_sound", None) or getattr(spec, "presentation", None)
            if look_obj and hasattr(self, "_lbl_look"):
                art = getattr(look_obj, "art_style", None) or getattr(look_obj, "visual_style", "Low-poly stylized")
                aud = getattr(look_obj, "audio_style", None) or getattr(look_obj, "music", "Procedural SFX & Ambient music")
                self._lbl_look.setText(f"Art style: {art} | Audio: {aud}")
            hud_obj = getattr(spec, "hud_and_menus", None) or getattr(spec, "ui", None)
            if hud_obj and hasattr(self, "_lbl_hud"):
                hud_elems = getattr(hud_obj, "hud_elements", None) or getattr(hud_obj, "elements", None)
                menus = getattr(hud_obj, "menus", None)
                hud_str = ", ".join(str(x) for x in hud_elems) if isinstance(hud_elems, (list, tuple)) and hud_elems else "Reticle, Score, Health bar"
                menu_str = ", ".join(str(x) for x in menus) if isinstance(menus, (list, tuple)) and menus else "Pause, Game Over screen"
                self._lbl_hud.setText(f"HUD: {hud_str} | Menus: {menu_str}")
            tech_obj = getattr(spec, "tech_budgets", None) or getattr(spec, "budgets", None) or getattr(spec, "tech", None)
            if tech_obj and hasattr(self, "_lbl_tech"):
                fps = getattr(tech_obj, "target_fps", 60)
                draws = getattr(tech_obj, "max_draw_calls", 1500)
                mem = getattr(tech_obj, "memory_budget_gb", getattr(tech_obj, "max_memory_mb", 4096))
                mem_str = f"{mem} GB" if mem < 128 else f"{mem} MB"
                self._lbl_tech.setText(f"Target: {fps} FPS Win64 | Max draw calls: {draws} | Memory budget: {mem_str}")

            # Scenarios
            if spec.acceptance and spec.acceptance.scenarios:
                s_lines = [f"• {sc.scenario_id}: {sc.derived_from} ({'must-pass' if sc.must_pass else 'optional'})" for sc in spec.acceptance.scenarios]
                self._lbl_scenarios.setText("\n".join(s_lines))
            else:
                self._lbl_scenarios.setText("No scenarios generated yet.")

        finally:
            self._is_populating = False
        self._validate_form()

    def get_spec(self) -> Optional[GameDesignSpec]:
        """Return the current spec with edited form fields applied."""
        if not self._spec:
            return None
        try:
            self._apply_inputs_to_spec()
        except Exception as exc:
            logger.warning("Failed to apply form inputs to spec: %s", exc)
        return copy.deepcopy(self._spec)

    @staticmethod
    def _format_condition(c: Any) -> str:
        if isinstance(c, dict):
            stat = c.get("stat")
            op = c.get("op")
            val = c.get("value")
            if stat and op and val is not None:
                try:
                    v = int(val) if float(val).is_integer() else val
                except (ValueError, TypeError):
                    v = val
                return f"{stat} {op} {v}"
            if c.get("kind") == "count_at_least" or ("n" in c and "event" in c):
                return f"count({c['event']}) >= {c['n']}"
            if "event" in c:
                return f"event={c['event']}"
            if "seconds" in c:
                return f"time >= {c['seconds']}"
            return str(c)
        if hasattr(c, "stat") and hasattr(c, "op") and hasattr(c, "value"):
            try:
                v = int(c.value) if getattr(c, "value", None) is not None and float(c.value).is_integer() else c.value
            except (ValueError, TypeError):
                v = c.value
            return f"{c.stat} {c.op} {v}"
        if getattr(c, "kind", "") == "count_at_least" or (hasattr(c, "n") and hasattr(c, "event")):
            return f"count({c.event}) >= {c.n}"
        if hasattr(c, "event"):
            return f"event={c.event}"
        if hasattr(c, "seconds"):
            return f"time >= {c.seconds}"
        return str(c)

    @classmethod
    def _parse_conditions_text(cls, text: str, existing_conditions: List[Any]) -> List[Any]:
        existing_map = {cls._format_condition(c): c for c in existing_conditions}
        existing_map_repr = {str(c): c for c in existing_conditions}
        parsed = []
        for part in text.split(","):
            p = part.strip()
            if not p:
                continue
            if p in existing_map:
                parsed.append(existing_map[p])
                continue
            if p in existing_map_repr:
                parsed.append(existing_map_repr[p])
                continue
            m = re.match(r"^([A-Za-z0-9_.]+)\s*(>=|<=|>|<|==)\s*(-?[0-9.]+)$", p)
            if m:
                from ...design.gds import StatCompare
                stat_name, op, val = m.group(1).lower(), m.group(2), float(m.group(3))
                # Normalize common shorthand stats
                if stat_name in ("health", "lives", "stamina", "max_health", "mana", "oxygen", "energy", "shield", "fuel", "heat", "sanity", "rage", "stealth", "hydration", "hunger"):
                    stat_name = f"player.{stat_name}"
                elif stat_name in ("score", "time_s"):
                    stat_name = f"game.{stat_name}"
                elif not (stat_name.startswith("player.") or stat_name.startswith("game.") or stat_name.startswith("entity.")):
                    if any(stat_name.endswith(sfx) for sfx in (".collected", ".remaining", ".killed")):
                        stat_name = f"entity.{stat_name}"
                parsed.append(StatCompare(stat=stat_name, op=op, value=val))
                continue
            m_cnt = re.match(r"^count\(\s*([A-Za-z0-9_.]+)\s*\)\s*(>=|==)\s*([0-9]+)$", p, re.IGNORECASE)
            if m_cnt:
                from ...design.gds import CountAtLeast
                parsed.append(CountAtLeast(kind="count_at_least", event=m_cnt.group(1).lower(), n=int(m_cnt.group(3))))
                continue
            m_ev = re.match(r"^event[=:]\s*([A-Za-z0-9_.]+)$", p, re.IGNORECASE)
            if m_ev:
                from ...design.gds import EventOccurred
                parsed.append(EventOccurred(kind="event", event=m_ev.group(1).lower()))
                continue
            m_time = re.match(r"^time\s*(>=|>|==)\s*([0-9.]+)$", p, re.IGNORECASE)
            if m_time:
                from ...design.gds import TimerElapsed
                parsed.append(TimerElapsed(kind="timer", seconds=float(m_time.group(2))))
                continue
            raise ValueError(f"Invalid condition syntax: '{p}' (expected format: stat op value)")
        return parsed

    def _apply_inputs_to_spec(self) -> None:
        if not self._spec:
            return
        # Apply overview title
        if hasattr(self, "_edit_title") and hasattr(self._spec, "meta") and self._spec.meta:
            title_text = self._edit_title.text().strip()
            if title_text:
                self._spec.meta.title = title_text

        # Apply overview fields
        genre_str = self._combo_genre.currentData() or "action_adventure"
        try:
            self._spec.overview.genre = Genre(genre_str)
        except Exception:
            pass

        cam_str = self._combo_camera.currentData() or "third_person"
        try:
            self._spec.overview.camera = CameraKind(cam_str)
        except Exception:
            pass

        try:
            self._spec.overview.session_minutes = self._spin_session.value()
        except Exception:
            pass

        try:
            self._spec.overview.players = self._spin_players.value()
        except Exception:
            pass

        try:
            self._spec.overview.pitch = self._edit_pitch.toPlainText().strip()
        except Exception:
            pass

        win_txt = self._edit_win.text().strip()
        if win_txt:
            self._spec.goals.win = self._parse_conditions_text(win_txt, self._spec.goals.win)
        else:
            self._spec.goals.win = []

        lose_txt = self._edit_lose.text().strip()
        if lose_txt:
            self._spec.goals.lose = self._parse_conditions_text(lose_txt, self._spec.goals.lose)
        else:
            self._spec.goals.lose = []

    @Slot()
    def _on_field_changed(self) -> None:
        if self._is_populating:
            return
        self.changed.emit()
        self._debounce_timer.start()

    @Slot()
    def _validate_form(self) -> None:
        if not self._spec:
            self.validationChanged.emit(True, [])
            return
        try:
            self._apply_inputs_to_spec()
            # Fast pydantic validation
            data = self._spec.model_dump()
            GameDesignSpec.model_validate(data)
            self.validationChanged.emit(True, [])
        except Exception as exc:
            err_msg = str(exc)
            lines = [l.strip() for l in err_msg.split("\n") if l.strip()]
            self.validationChanged.emit(False, lines[:3])

    @Slot()
    def _on_add_rule_clicked(self) -> None:
        self._apply_inputs_to_spec()
        entity_ids = [e.entity_id for e in self._spec.entities] if self._spec else []
        dlg = RuleEditorDialog(entity_ids=entity_ids, parent=self)
        if self._spec and self._spec.rules:
            existing_ids = {r.rule_id for r in self._spec.rules}
            next_idx = len(self._spec.rules) + 1
            while f"rule_{next_idx}" in existing_ids:
                next_idx += 1
            dlg._id_input.setText(f"rule_{next_idx}")
        if dlg.exec() == RuleEditorDialog.Accepted:
            new_rule = dlg.get_rule_spec()
            if self._spec:
                self._spec.rules.append(new_rule)
                self.set_spec(self._spec)
                self.changed.emit()

    def _on_edit_rule_clicked(self, row: int) -> None:
        if not self._spec or not (0 <= row < len(self._spec.rules)):
            return
        self._apply_inputs_to_spec()
        rule = self._spec.rules[row]
        entity_ids = [e.entity_id for e in self._spec.entities]
        dlg = RuleEditorDialog(rule=rule, entity_ids=entity_ids, parent=self)
        if dlg.exec() == RuleEditorDialog.Accepted:
            updated_rule = dlg.get_rule_spec()
            self._spec.rules[row] = updated_rule
            self.set_spec(self._spec)
            self.changed.emit()
