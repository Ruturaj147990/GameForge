"""Structured rule editor dialog for GDS rules (spec §4.3, WI-4.6)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from src.gameforge_ide.design.gds import (
    AddStat,
    Condition,
    CountAtLeast,
    EndGame,
    EventRef,
    RuleSpec,
    SetStat,
    StatCompare,
)
from src.gameforge_ide.design.render import EVENT_PHRASES, sentence


def format_rule_sentence(rule: RuleSpec) -> str:
    """Format a RuleSpec as a natural-language sentence."""
    ev = rule.when.event if (rule.when and rule.when.event) else "event occurs"
    trigger_phrase = EVENT_PHRASES.get(ev, ev)
    src_str = f" from {rule.when.source}" if (rule.when and rule.when.source) else ""
    cond_str = f" if {', '.join(sentence(c) for c in rule.conditions)}" if rule.conditions else ""
    eff_str = ", ".join(sentence(eff) for eff in rule.effects) if rule.effects else "do nothing"
    return f"When {trigger_phrase}{src_str}{cond_str} then {eff_str}."


class RuleEditorDialog(QDialog):
    """Structured visual builder for GDS rules: When [event] / If [conditions] / Then [effects]."""

    def __init__(
        self,
        rule: Optional[RuleSpec] = None,
        entity_ids: Optional[List[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ruleEditorDialog")
        self.setAccessibleName("Structured rule editor")
        self.setWindowTitle("Edit Rule" if rule else "Add Rule")
        self.setModal(True)
        self.resize(600, 560)
        self.setStyleSheet(
            f"QDialog#{self.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  border: 1px solid {tokens.BORDER};"
            f"}}"
        )

        self._rule = rule
        self._entity_ids = entity_ids or []
        self._target_stat = "game.score"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG)
        layout.setSpacing(tokens.SPACE_MD)

        # Title
        title_lbl = QLabel("Rule Definition & Logic Builder", self)
        title_lbl.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY};"
            f"font-size: {tokens.FONT_HEADING_SM}px;"
            f"font-weight: 700;"
        )
        layout.addWidget(title_lbl)

        # Rule ID
        id_layout = QHBoxLayout()
        lbl_id = QLabel("Rule ID:", self)
        lbl_id.setFixedWidth(80)
        lbl_id.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")
        self._id_input = QLineEdit(self)
        self._id_input.setObjectName("ruleIdInput")
        self._id_input.setAccessibleName("Rule identifier")
        self._id_input.setText(rule.rule_id if rule else "rule_1")
        self._id_input.setStyleSheet(self._input_style())
        self._id_input.textChanged.connect(self._on_input_changed)
        id_layout.addWidget(lbl_id)
        id_layout.addWidget(self._id_input)
        layout.addLayout(id_layout)

        # ── 1. When Trigger Event ─────────────────────────────────────────────
        when_layout = QHBoxLayout()
        lbl_when = QLabel("When:", self)
        lbl_when.setFixedWidth(80)
        lbl_when.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")
        self._event_combo = QComboBox(self)
        self._event_combo.setObjectName("ruleEventCombo")
        self._event_combo.setAccessibleName("Trigger event")
        self._event_combo.setEditable(True)
        events = [
            "pickup.collected",
            "guard.spotted",
            "combat.hit",
            "combat.death",
            "player.spawned",
            "timer.elapsed",
            "goal.reached",
            "level.loaded",
        ]
        self._event_combo.addItems(events)
        if rule and rule.when and rule.when.event:
            if rule.when.event not in events:
                self._event_combo.addItem(rule.when.event)
            self._event_combo.setCurrentText(rule.when.event)
        self._event_combo.setStyleSheet(self._input_style())
        self._event_combo.currentTextChanged.connect(self._on_input_changed)
        when_layout.addWidget(lbl_when)
        when_layout.addWidget(self._event_combo, 1)

        # Optional source entity
        lbl_source = QLabel("From Entity:", self)
        lbl_source.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._source_combo = QComboBox(self)
        self._source_combo.setObjectName("ruleSourceCombo")
        self._source_combo.setAccessibleName("Source entity target")
        self._source_combo.addItem("Any entity", userData=None)
        for eid in self._entity_ids:
            self._source_combo.addItem(eid, userData=eid)
        if rule and rule.when and rule.when.source:
            if rule.when.source not in self._entity_ids:
                self._source_combo.addItem(rule.when.source, userData=rule.when.source)
            self._source_combo.setCurrentText(rule.when.source)
        self._source_combo.setStyleSheet(self._input_style())
        self._source_combo.currentIndexChanged.connect(self._on_input_changed)
        when_layout.addWidget(lbl_source)
        when_layout.addWidget(self._source_combo)
        layout.addLayout(when_layout)

        # ── 2. If Condition (Optional Condition Builder) ─────────────────────
        cond_layout = QHBoxLayout()
        lbl_if = QLabel("If (Cond):", self)
        lbl_if.setFixedWidth(80)
        lbl_if.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")
        cond_layout.addWidget(lbl_if)

        self._cond_type_combo = QComboBox(self)
        self._cond_type_combo.setObjectName("ruleCondTypeCombo")
        self._cond_type_combo.setAccessibleName("Condition kind")
        self._cond_type_combo.addItems(["No Condition", "Stat Comparison", "Event Count At Least"])
        self._cond_type_combo.setStyleSheet(self._input_style())
        cond_layout.addWidget(self._cond_type_combo)

        # Stat compare controls
        self._cond_stat_input = QLineEdit(self)
        self._cond_stat_input.setObjectName("ruleCondStatInput")
        self._cond_stat_input.setPlaceholderText("player.health")
        self._cond_stat_input.setFixedWidth(110)
        self._cond_stat_input.setStyleSheet(self._input_style())
        self._cond_stat_input.textChanged.connect(self._on_input_changed)
        cond_layout.addWidget(self._cond_stat_input)

        self._cond_op_combo = QComboBox(self)
        self._cond_op_combo.setObjectName("ruleCondOpCombo")
        self._cond_op_combo.addItems([">=", ">", "==", "<=", "<"])
        self._cond_op_combo.setFixedWidth(60)
        self._cond_op_combo.setStyleSheet(self._input_style())
        self._cond_op_combo.currentIndexChanged.connect(self._on_input_changed)
        cond_layout.addWidget(self._cond_op_combo)

        self._cond_val_spin = QSpinBox(self)
        self._cond_val_spin.setObjectName("ruleCondValSpin")
        self._cond_val_spin.setRange(-9999, 9999)
        self._cond_val_spin.setValue(0)
        self._cond_val_spin.setFixedWidth(70)
        self._cond_val_spin.setStyleSheet(self._input_style())
        self._cond_val_spin.valueChanged.connect(self._on_input_changed)
        cond_layout.addWidget(self._cond_val_spin)

        # Event count controls
        self._cond_event_input = QLineEdit(self)
        self._cond_event_input.setObjectName("ruleCondEventInput")
        self._cond_event_input.setPlaceholderText("event name (e.g. pickup.collected)")
        self._cond_event_input.setStyleSheet(self._input_style())
        self._cond_event_input.textChanged.connect(self._on_input_changed)
        self._cond_event_input.setVisible(False)
        cond_layout.addWidget(self._cond_event_input, 1)

        self._cond_count_spin = QSpinBox(self)
        self._cond_count_spin.setObjectName("ruleCondCountSpin")
        self._cond_count_spin.setRange(1, 9999)
        self._cond_count_spin.setValue(1)
        self._cond_count_spin.setFixedWidth(70)
        self._cond_count_spin.setStyleSheet(self._input_style())
        self._cond_count_spin.valueChanged.connect(self._on_input_changed)
        self._cond_count_spin.setVisible(False)
        cond_layout.addWidget(self._cond_count_spin)

        self._cond_type_combo.currentTextChanged.connect(self._on_cond_type_changed)
        layout.addLayout(cond_layout)

        # Populate condition if rule has existing conditions
        if rule and getattr(rule, "conditions", None) and len(rule.conditions) > 0:
            c0 = rule.conditions[0]
            if isinstance(c0, StatCompare) or (hasattr(c0, "stat") and hasattr(c0, "op") and hasattr(c0, "value")):
                self._cond_type_combo.setCurrentText("Stat Comparison")
                self._cond_stat_input.setText(str(getattr(c0, "stat", "player.health")))
                self._cond_op_combo.setCurrentText(str(getattr(c0, "op", ">=")))
                self._cond_val_spin.setValue(int(getattr(c0, "value", 0)))
            elif isinstance(c0, CountAtLeast) or getattr(c0, "kind", "") == "count_at_least":
                self._cond_type_combo.setCurrentText("Event Count At Least")
                self._cond_event_input.setText(str(getattr(c0, "event", "pickup.collected")))
                self._cond_count_spin.setValue(int(getattr(c0, "n", 1)))
        else:
            self._cond_type_combo.setCurrentText("No Condition")
            self._cond_stat_input.setVisible(False)
            self._cond_op_combo.setVisible(False)
            self._cond_val_spin.setVisible(False)
            self._cond_event_input.setVisible(False)
            self._cond_count_spin.setVisible(False)

        # ── 3. Then Effect ────────────────────────────────────────────────────
        effect_layout = QHBoxLayout()
        lbl_then = QLabel("Then:", self)
        lbl_then.setFixedWidth(80)
        lbl_then.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")

        self._effect_type_combo = QComboBox(self)
        self._effect_type_combo.setObjectName("ruleEffectTypeCombo")
        self._effect_type_combo.setAccessibleName("Effect action")
        self._effect_type_combo.addItems(["Add Score / Stat", "Set Stat", "End Game (Win)", "End Game (Lose)"])
        self._effect_type_combo.setStyleSheet(self._input_style())
        effect_layout.addWidget(lbl_then)
        effect_layout.addWidget(self._effect_type_combo, 1)

        self._lbl_stat = QLabel("Stat:", self)
        self._lbl_stat.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        effect_layout.addWidget(self._lbl_stat)

        self._stat_input = QLineEdit(self)
        self._stat_input.setObjectName("ruleStatInput")
        self._stat_input.setAccessibleName("Target stat name")
        self._stat_input.setText("game.score")
        self._stat_input.setPlaceholderText("stat (e.g. game.score)")
        self._stat_input.setFixedWidth(130)
        self._stat_input.setStyleSheet(self._input_style())
        self._stat_input.textChanged.connect(self._on_input_changed)
        effect_layout.addWidget(self._stat_input)

        self._delta_spin = QSpinBox(self)
        self._delta_spin.setObjectName("ruleDeltaSpin")
        self._delta_spin.setAccessibleName("Effect value or delta")
        self._delta_spin.setRange(-1000, 1000)
        self._delta_spin.setValue(10)
        self._delta_spin.setStyleSheet(self._input_style())
        self._delta_spin.valueChanged.connect(self._on_input_changed)
        effect_layout.addWidget(self._delta_spin)
        layout.addLayout(effect_layout)

        # Restore existing effect state if rule provided
        if rule and rule.effects:
            eff0 = rule.effects[0]
            if isinstance(eff0, EndGame) or getattr(eff0, "kind", "") == "end_game":
                outcome = getattr(eff0, "outcome", "win")
                self._effect_type_combo.setCurrentText("End Game (Win)" if outcome == "win" else "End Game (Lose)")
                self._delta_spin.setVisible(False)
                self._lbl_stat.setVisible(False)
                self._stat_input.setVisible(False)
            elif isinstance(eff0, SetStat) or getattr(eff0, "kind", "") == "set_stat":
                self._effect_type_combo.setCurrentText("Set Stat")
                self._delta_spin.setValue(int(getattr(eff0, "value", 100)))
                self._target_stat = getattr(eff0, "stat", "player.health")
                self._stat_input.setText(self._target_stat)
                self._delta_spin.setVisible(True)
                self._lbl_stat.setVisible(True)
                self._stat_input.setVisible(True)
            elif isinstance(eff0, AddStat) or getattr(eff0, "kind", "") == "add_stat":
                self._effect_type_combo.setCurrentText("Add Score / Stat")
                self._delta_spin.setValue(int(getattr(eff0, "delta", 10)))
                self._target_stat = getattr(eff0, "stat", "game.score")
                self._stat_input.setText(self._target_stat)
                self._delta_spin.setVisible(True)
                self._lbl_stat.setVisible(True)
                self._stat_input.setVisible(True)
        else:
            self._delta_spin.setVisible(True)
            self._lbl_stat.setVisible(True)
            self._stat_input.setVisible(True)

        self._effect_type_combo.currentTextChanged.connect(self._on_effect_type_changed)

        # ── 4. Description ───────────────────────────────────────────────────
        desc_layout = QHBoxLayout()
        lbl_desc = QLabel("Description:", self)
        lbl_desc.setFixedWidth(80)
        lbl_desc.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")
        self._desc_input = QLineEdit(self)
        self._desc_input.setObjectName("ruleDescInput")
        self._desc_input.setAccessibleName("Rule description")
        self._desc_input.setPlaceholderText("e.g. Award points on pickup")
        self._desc_input.setText(rule.description if rule else "")
        self._desc_input.setStyleSheet(self._input_style())
        self._desc_input.textChanged.connect(self._on_input_changed)
        desc_layout.addWidget(lbl_desc)
        desc_layout.addWidget(self._desc_input)
        layout.addLayout(desc_layout)

        # ── 5. Live Sentence Preview Card ─────────────────────────────────────
        preview_box = QFrame(self)
        preview_box.setObjectName("rulePreviewBox")
        preview_box.setStyleSheet(
            f"QFrame#{preview_box.objectName()} {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: {tokens.SPACE_SM}px;"
            f"}}"
        )
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM)
        preview_layout.setSpacing(tokens.SPACE_XS)

        lbl_prev_title = QLabel("Live Rule Sentence Preview:", preview_box)
        lbl_prev_title.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600;")
        preview_layout.addWidget(lbl_prev_title)

        self._lbl_sentence_preview = QLabel("", preview_box)
        self._lbl_sentence_preview.setObjectName("ruleSentencePreview")
        self._lbl_sentence_preview.setWordWrap(True)
        self._lbl_sentence_preview.setStyleSheet(
            f"color: {tokens.ACCENT_PRIMARY}; font-size: {tokens.FONT_BODY}px; font-weight: 600;"
        )
        preview_layout.addWidget(self._lbl_sentence_preview)
        layout.addWidget(preview_box)

        # Inline validation error label
        self._lbl_val_error = QLabel("", self)
        self._lbl_val_error.setObjectName("ruleValError")
        self._lbl_val_error.setWordWrap(True)
        self._lbl_val_error.setStyleSheet(f"color: {tokens.ACCENT_ERROR}; font-size: {tokens.FONT_BODY_SM}px;")
        self._lbl_val_error.setVisible(False)
        layout.addWidget(self._lbl_val_error)

        layout.addStretch(1)

        # ── 6. Action Buttons ─────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        self._btn_cancel = QPushButton("Cancel", self)
        self._btn_cancel.setObjectName("btnCancelRule")
        self._btn_cancel.setAccessibleName("Cancel rule editing")
        self._btn_cancel.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.BG_HOVER}; }}"
        )
        self._btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_cancel)

        self._btn_save = QPushButton("Save Rule", self)
        self._btn_save.setObjectName("btnSaveRule")
        self._btn_save.setAccessibleName("Save validated rule")
        self._btn_save.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.ACCENT_PRIMARY};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px;"
            f"  font-weight: 600;"
            f"}}"
            f"QPushButton:hover {{ background-color: {tokens.ACCENT_HOVER}; }}"
        )
        self._btn_save.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self._btn_save)

        layout.addLayout(btn_layout)

        # Initialize live preview
        self._update_sentence_preview()

    @staticmethod
    def _input_style() -> str:
        return (
            f"background-color: {tokens.BG_SURFACE};"
            f"color: {tokens.TEXT_PRIMARY};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"padding: 4px {tokens.SPACE_SM}px;"
            f"font-size: {tokens.FONT_BODY}px;"
        )

    @Slot(str)
    def _on_cond_type_changed(self, t: str) -> None:
        is_stat = (t == "Stat Comparison")
        is_count = (t == "Event Count At Least")
        self._cond_stat_input.setVisible(is_stat)
        self._cond_op_combo.setVisible(is_stat)
        self._cond_val_spin.setVisible(is_stat)
        self._cond_event_input.setVisible(is_count)
        self._cond_count_spin.setVisible(is_count)
        self._update_sentence_preview()

    @Slot(str)
    def _on_effect_type_changed(self, t: str) -> None:
        is_stat = t in ("Add Score / Stat", "Set Stat")
        self._delta_spin.setVisible(is_stat)
        self._lbl_stat.setVisible(is_stat)
        self._stat_input.setVisible(is_stat)
        self._update_sentence_preview()

    @Slot()
    def _on_input_changed(self) -> None:
        self._update_sentence_preview()

    def _update_sentence_preview(self) -> None:
        try:
            temp_rule = self.get_rule_spec()
            s_text = format_rule_sentence(temp_rule)
            self._lbl_sentence_preview.setText(f'"{s_text}"')
            self._lbl_val_error.setVisible(False)
        except Exception as exc:
            ev = self._event_combo.currentText().strip() or "event"
            self._lbl_sentence_preview.setText(f'Draft: When {ev} ...')

    def _validate(self) -> Optional[str]:
        """Validate dialog inputs before saving."""
        rid = self._id_input.text().strip()
        if not rid:
            return "Rule ID cannot be empty."
        if not re.match(r"^[A-Za-z0-9_]+$", rid):
            return "Rule ID must contain only alphanumeric characters and underscores."

        ev = self._event_combo.currentText().strip()
        if not ev:
            return "When event cannot be empty."

        cond_type = self._cond_type_combo.currentText()
        if cond_type == "Stat Comparison":
            stat = self._cond_stat_input.text().strip()
            if not stat:
                return "Condition stat name cannot be empty."
        elif cond_type == "Event Count At Least":
            cev = self._cond_event_input.text().strip()
            if not cev:
                return "Condition event name cannot be empty."

        eff_type = self._effect_type_combo.currentText()
        if eff_type in ("Add Score / Stat", "Set Stat"):
            stat = self._stat_input.text().strip()
            if not stat:
                return "Effect stat name cannot be empty."

        return None

    @Slot()
    def _on_save_clicked(self) -> None:
        err = self._validate()
        if err:
            self._lbl_val_error.setText(f"Validation Error: {err}")
            self._lbl_val_error.setVisible(True)
            return
        self._lbl_val_error.setVisible(False)
        self.accept()

    def get_rule_spec(self) -> RuleSpec:
        """Construct validated RuleSpec from dialog inputs."""
        rid = self._id_input.text().strip() or "rule_1"
        ev = self._event_combo.currentText().strip() or "pickup.collected"
        src = self._source_combo.currentData()

        eff_type = self._effect_type_combo.currentText()
        if eff_type == "End Game (Win)":
            effect = EndGame(kind="end_game", outcome="win")
        elif eff_type == "End Game (Lose)":
            effect = EndGame(kind="end_game", outcome="lose")
        elif eff_type == "Set Stat":
            stat_name = self._stat_input.text().strip() or self._target_stat or "player.health"
            if not (stat_name.startswith("player.") or stat_name.startswith("game.") or stat_name.startswith("entity.")):
                if stat_name in ("health", "lives", "stamina", "max_health"):
                    stat_name = f"player.{stat_name}"
                elif stat_name in ("score", "time_s"):
                    stat_name = f"game.{stat_name}"
                else:
                    stat_name = f"game.{stat_name}"
            effect = SetStat(kind="set_stat", stat=stat_name, value=float(self._delta_spin.value()))
        else:
            stat_name = self._stat_input.text().strip() or self._target_stat or "game.score"
            if not (stat_name.startswith("player.") or stat_name.startswith("game.") or stat_name.startswith("entity.")):
                if stat_name in ("health", "lives", "stamina", "max_health"):
                    stat_name = f"player.{stat_name}"
                elif stat_name in ("score", "time_s"):
                    stat_name = f"game.{stat_name}"
                else:
                    stat_name = f"game.{stat_name}"
            effect = AddStat(kind="add_stat", stat=stat_name, delta=float(self._delta_spin.value()))

        # Build conditions
        conds: List[Condition] = []
        cond_type = self._cond_type_combo.currentText()
        if cond_type == "Stat Comparison":
            stat_name = self._cond_stat_input.text().strip() or "player.health"
            if not (stat_name.startswith("player.") or stat_name.startswith("game.") or stat_name.startswith("entity.")):
                if stat_name in ("health", "lives", "stamina", "max_health"):
                    stat_name = f"player.{stat_name}"
                elif stat_name in ("score", "time_s"):
                    stat_name = f"game.{stat_name}"
                else:
                    stat_name = f"player.{stat_name}"
            op = self._cond_op_combo.currentText()
            val = float(self._cond_val_spin.value())
            conds.append(StatCompare(stat=stat_name, op=op, value=val))
        elif cond_type == "Event Count At Least":
            cev = self._cond_event_input.text().strip() or "pickup.collected"
            cnt = int(self._cond_count_spin.value())
            conds.append(CountAtLeast(kind="count_at_least", event=cev, n=cnt))
        elif self._rule and hasattr(self._rule, "conditions") and self._rule.conditions:
            # Preserve any complex non-standard conditions
            conds = list(self._rule.conditions)

        desc = self._desc_input.text().strip()
        trailing_effects = self._rule.effects[1:] if self._rule and len(self._rule.effects) > 1 else []
        return RuleSpec(
            rule_id=rid,
            when=EventRef(event=ev, source=src),
            conditions=conds,
            effects=[effect] + trailing_effects,
            description=desc,
        )
