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
from src.gameforge_ide.design.gds import (
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
from src.gameforge_ide.design.render import sentence

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
        self._toggle_btn = QPushButton(f"▶ {title}", self)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent;"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"  font-weight: 600;"
            f"  text-align: left;"
            f"}}"
            f"QPushButton:hover {{ color: {tokens.ACCENT_HOVER}; }}"
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
        self._toggle_btn.setText(f"{arrow} {self._title}")


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

        # ── 1. Overview Section ──────────────────────────────────────────────
        sec_overview = self._create_card("Overview", "cardOverview")
        olayout = QVBoxLayout(sec_overview)
        olayout.setContentsMargins(14, 14, 14, 14)
        olayout.setSpacing(tokens.SPACE_MD)

        row1 = QHBoxLayout()
        row1.setSpacing(tokens.SPACE_LG)

        # Genre combo
        vbox_genre = QVBoxLayout()
        lbl_genre = QLabel("Genre:", sec_overview)
        lbl_genre.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._combo_genre = QComboBox(sec_overview)
        self._combo_genre.setObjectName("gdsGenreCombo")
        for g in Genre:
            self._combo_genre.addItem(g.value.capitalize(), userData=g.value)
        self._combo_genre.currentIndexChanged.connect(self._on_field_changed)
        self._style_input(self._combo_genre)
        vbox_genre.addWidget(lbl_genre)
        vbox_genre.addWidget(self._combo_genre)
        row1.addLayout(vbox_genre, 1)

        # Camera combo
        vbox_cam = QVBoxLayout()
        lbl_cam = QLabel("Camera:", sec_overview)
        lbl_cam.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._combo_camera = QComboBox(sec_overview)
        self._combo_camera.setObjectName("gdsCameraCombo")
        for c in CameraKind:
            self._combo_camera.addItem(c.value.replace("_", " ").capitalize(), userData=c.value)
        self._combo_camera.currentIndexChanged.connect(self._on_field_changed)
        self._style_input(self._combo_camera)
        vbox_cam.addWidget(lbl_cam)
        vbox_cam.addWidget(self._combo_camera)
        row1.addLayout(vbox_cam, 1)

        # Session minutes
        vbox_session = QVBoxLayout()
        lbl_session = QLabel("Target Session (min):", sec_overview)
        lbl_session.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._spin_session = QSpinBox(sec_overview)
        self._spin_session.setObjectName("gdsSessionSpin")
        self._spin_session.setRange(1, 180)
        self._spin_session.setValue(10)
        self._spin_session.valueChanged.connect(self._on_field_changed)
        self._style_input(self._spin_session)
        vbox_session.addWidget(lbl_session)
        vbox_session.addWidget(self._spin_session)
        row1.addLayout(vbox_session, 1)

        # Players
        vbox_players = QVBoxLayout()
        lbl_players = QLabel("Players:", sec_overview)
        lbl_players.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._spin_players = QSpinBox(sec_overview)
        self._spin_players.setObjectName("gdsPlayersSpin")
        self._spin_players.setRange(1, 8)
        self._spin_players.setValue(1)
        self._spin_players.valueChanged.connect(self._on_field_changed)
        self._style_input(self._spin_players)
        vbox_players.addWidget(lbl_players)
        vbox_players.addWidget(self._spin_players)
        row1.addLayout(vbox_players, 1)

        olayout.addLayout(row1)

        # Pitch
        vbox_pitch = QVBoxLayout()
        lbl_pitch = QLabel("Pitch:", sec_overview)
        lbl_pitch.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._edit_pitch = QPlainTextEdit(sec_overview)
        self._edit_pitch.setObjectName("gdsPitchInput")
        self._edit_pitch.setFixedHeight(60)
        self._edit_pitch.textChanged.connect(self._on_field_changed)
        self._style_input(self._edit_pitch)
        vbox_pitch.addWidget(lbl_pitch)
        vbox_pitch.addWidget(self._edit_pitch)
        olayout.addLayout(vbox_pitch)

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
        lbl_look = QLabel("Art style: Low-poly stylized | Audio: Procedural SFX & Ambient music", self._sec_look_sound)
        lbl_look.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._sec_look_sound.add_widget(lbl_look)
        main_layout.addWidget(self._sec_look_sound)

        self._sec_hud_menus = CollapsibleSection("HUD & Menus", self, object_name="secHudMenus")
        lbl_hud = QLabel("HUD: Reticle, Score, Health bar | Menus: Pause, Game Over screen", self._sec_hud_menus)
        lbl_hud.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._sec_hud_menus.add_widget(lbl_hud)
        main_layout.addWidget(self._sec_hud_menus)

        self._sec_tech = CollapsibleSection("Tech & Budgets", self, object_name="secTech")
        lbl_tech = QLabel("Target: 60 FPS Win64 | Max draw calls: 1500 | Memory budget: 4 GB", self._sec_tech)
        lbl_tech.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._sec_tech.add_widget(lbl_tech)
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

    def set_spec(self, spec: GameDesignSpec) -> None:
        """Populate form with GameDesignSpec data."""
        self._spec = copy.deepcopy(spec)
        self._is_populating = True
        try:
            # Overview
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
                self._table_levels.setItem(r, 0, QTableWidgetItem(lvl.level_id))
                layout_str = lvl.layout.value if hasattr(lvl.layout, "value") else str(lvl.layout)
                self._table_levels.setItem(r, 1, QTableWidgetItem(layout_str))
                sz = f"{lvl.size_m.x}x{lvl.size_m.y}" if lvl.size_m else "—"
                self._table_levels.setItem(r, 2, QTableWidgetItem(sz))
                lighting_str = lvl.lighting.value if hasattr(lvl.lighting, "value") else str(lvl.lighting or "day")
                self._table_levels.setItem(r, 3, QTableWidgetItem(lighting_str))

            # Entities
            self._table_entities.setRowCount(len(spec.entities))
            for r, ent in enumerate(spec.entities):
                self._table_entities.setItem(r, 0, QTableWidgetItem(ent.entity_id))
                kind_str = ent.kind.value if hasattr(ent.kind, "value") else str(ent.kind)
                self._table_entities.setItem(r, 1, QTableWidgetItem(kind_str))
                self._table_entities.setItem(r, 2, QTableWidgetItem(str(ent.count)))
                self._table_entities.setItem(r, 3, QTableWidgetItem(ent.module or "kit"))
                plc = ent.placement.strategy if ent.placement else "default"
                self._table_entities.setItem(r, 4, QTableWidgetItem(str(plc)))

            # Rules
            self._table_rules.setRowCount(len(spec.rules))
            for r, rule in enumerate(spec.rules):
                s_text = sentence(rule) if rule else ""
                self._table_rules.setItem(r, 0, QTableWidgetItem(s_text))
                btn_edit = QPushButton("Edit", self._table_rules)
                btn_edit.setStyleSheet(
                    f"background-color: {tokens.BG_SURFACE}; color: {tokens.TEXT_PRIMARY};"
                    f"border: 1px solid {tokens.BORDER}; border-radius: 4px; padding: 2px 6px;"
                )
                btn_edit.clicked.connect(lambda _, row=r: self._on_edit_rule_clicked(row))
                self._table_rules.setCellWidget(r, 1, btn_edit)

            # Goals
            win_texts = [c.stat if hasattr(c, "stat") else str(c) for c in spec.goals.win]
            lose_texts = [c.stat if hasattr(c, "stat") else str(c) for c in spec.goals.lose]
            self._edit_win.setText(", ".join(win_texts) if win_texts else "relics.collected >= 5")
            self._edit_lose.setText(", ".join(lose_texts) if lose_texts else "player.health <= 0")

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

    def _apply_inputs_to_spec(self) -> None:
        if not self._spec:
            return
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

        try:
            win_txt = self._edit_win.text().strip()
            if win_txt:
                parsed_win = []
                for part in win_txt.split(","):
                    p = part.strip()
                    m = re.match(r"^([a-z0-9_.]+)\s*(>=|<=|>|<|==|!=)\s*([0-9.]+)$", p)
                    if m:
                        from ...design.gds import StatCompare
                        stat_name, op, val = m.group(1), m.group(2), float(m.group(3))
                        parsed_win.append(StatCompare(stat=stat_name, op=op, value=val))
                if parsed_win:
                    self._spec.goals.win = parsed_win
        except Exception as exc:
            logger.debug("Could not parse win conditions: %s", exc)

        try:
            lose_txt = self._edit_lose.text().strip()
            if lose_txt:
                parsed_lose = []
                for part in lose_txt.split(","):
                    p = part.strip()
                    m = re.match(r"^([a-z0-9_.]+)\s*(>=|<=|>|<|==|!=)\s*([0-9.]+)$", p)
                    if m:
                        from ...design.gds import StatCompare
                        stat_name, op, val = m.group(1), m.group(2), float(m.group(3))
                        parsed_lose.append(StatCompare(stat=stat_name, op=op, value=val))
                if parsed_lose:
                    self._spec.goals.lose = parsed_lose
        except Exception as exc:
            logger.debug("Could not parse lose conditions: %s", exc)

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
        entity_ids = [e.entity_id for e in self._spec.entities] if self._spec else []
        dlg = RuleEditorDialog(entity_ids=entity_ids, parent=self)
        if dlg.exec() == RuleEditorDialog.Accepted:
            new_rule = dlg.get_rule_spec()
            if self._spec:
                self._spec.rules.append(new_rule)
                self.set_spec(self._spec)
                self.changed.emit()

    def _on_edit_rule_clicked(self, row: int) -> None:
        if not self._spec or not (0 <= row < len(self._spec.rules)):
            return
        rule = self._spec.rules[row]
        entity_ids = [e.entity_id for e in self._spec.entities]
        dlg = RuleEditorDialog(rule=rule, entity_ids=entity_ids, parent=self)
        if dlg.exec() == RuleEditorDialog.Accepted:
            updated_rule = dlg.get_rule_spec()
            self._spec.rules[row] = updated_rule
            self.set_spec(self._spec)
            self.changed.emit()
