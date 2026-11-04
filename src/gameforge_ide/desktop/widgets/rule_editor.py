"""Structured rule editor dialog for GDS rules (spec §4.3, WI-4.6)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from src.gameforge_ide.design.gds import AddStat, EndGame, EventRef, RuleSpec


class RuleEditorDialog(QDialog):
    """Structured editor for GDS rules: When [event] / If [conditions] / Then [effects]."""

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
        self.resize(520, 400)
        self.setStyleSheet(
            f"QDialog#{self.objectName()} {{"
            f"  background-color: {tokens.BG_ROOT};"
            f"  border: 1px solid {tokens.BORDER};"
            f"}}"
        )

        self._rule = rule
        self._entity_ids = entity_ids or []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG)
        layout.setSpacing(tokens.SPACE_MD)

        # Title
        title_lbl = QLabel("Rule Definition", self)
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
        self._id_input.setText(rule.rule_id if rule else "rule_1")
        self._id_input.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE};"
            f"color: {tokens.TEXT_PRIMARY};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"padding: 4px {tokens.SPACE_SM}px;"
        )
        id_layout.addWidget(lbl_id)
        id_layout.addWidget(self._id_input)
        layout.addLayout(id_layout)

        # When Event
        when_layout = QHBoxLayout()
        lbl_when = QLabel("When:", self)
        lbl_when.setFixedWidth(80)
        lbl_when.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")
        self._event_combo = QComboBox(self)
        self._event_combo.setObjectName("ruleEventCombo")
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
        if rule and rule.when.event in events:
            self._event_combo.setCurrentText(rule.when.event)
        self._event_combo.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE};"
            f"color: {tokens.TEXT_PRIMARY};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"padding: 4px {tokens.SPACE_SM}px;"
        )
        when_layout.addWidget(lbl_when)
        when_layout.addWidget(self._event_combo, 1)

        # Optional source entity
        lbl_source = QLabel("From Entity:", self)
        lbl_source.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px;")
        self._source_combo = QComboBox(self)
        self._source_combo.setObjectName("ruleSourceCombo")
        self._source_combo.addItem("Any entity", userData=None)
        for eid in self._entity_ids:
            self._source_combo.addItem(eid, userData=eid)
        if rule and rule.when.source in self._entity_ids:
            self._source_combo.setCurrentText(rule.when.source)
        self._source_combo.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE};"
            f"color: {tokens.TEXT_PRIMARY};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"padding: 4px {tokens.SPACE_SM}px;"
        )
        when_layout.addWidget(lbl_source)
        when_layout.addWidget(self._source_combo)
        layout.addLayout(when_layout)

        # Then Effect
        effect_layout = QHBoxLayout()
        lbl_then = QLabel("Then:", self)
        lbl_then.setFixedWidth(80)
        lbl_then.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")

        self._effect_type_combo = QComboBox(self)
        self._effect_type_combo.setObjectName("ruleEffectTypeCombo")
        self._effect_type_combo.addItems(["Add Score / Stat", "End Game (Win)", "End Game (Lose)"])
        self._effect_type_combo.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE};"
            f"color: {tokens.TEXT_PRIMARY};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"padding: 4px {tokens.SPACE_SM}px;"
        )
        effect_layout.addWidget(lbl_then)
        effect_layout.addWidget(self._effect_type_combo, 1)

        self._delta_spin = QSpinBox(self)
        self._delta_spin.setObjectName("ruleDeltaSpin")
        self._delta_spin.setRange(-1000, 1000)
        self._delta_spin.setValue(10)
        self._delta_spin.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE};"
            f"color: {tokens.TEXT_PRIMARY};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"padding: 4px {tokens.SPACE_SM}px;"
        )
        effect_layout.addWidget(self._delta_spin)
        layout.addLayout(effect_layout)

        # Restore existing effect state if rule provided
        if rule and rule.effects:
            eff0 = rule.effects[0]
            if isinstance(eff0, EndGame) or getattr(eff0, "kind", "") == "end_game":
                outcome = getattr(eff0, "outcome", "win")
                self._effect_type_combo.setCurrentText("End Game (Win)" if outcome == "win" else "End Game (Lose)")
                self._delta_spin.setVisible(False)
            elif isinstance(eff0, AddStat) or getattr(eff0, "kind", "") == "add_stat":
                self._effect_type_combo.setCurrentText("Add Score / Stat")
                self._delta_spin.setValue(int(getattr(eff0, "delta", 10)))
                self._delta_spin.setVisible(True)
        else:
            self._delta_spin.setVisible(True)

        self._effect_type_combo.currentTextChanged.connect(
            lambda t: self._delta_spin.setVisible(t == "Add Score / Stat")
        )

        # Description
        desc_layout = QHBoxLayout()
        lbl_desc = QLabel("Description:", self)
        lbl_desc.setFixedWidth(80)
        lbl_desc.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY}px;")
        self._desc_input = QLineEdit(self)
        self._desc_input.setObjectName("ruleDescInput")
        self._desc_input.setPlaceholderText("e.g. Award points on pickup")
        self._desc_input.setText(rule.description if rule else "")
        self._desc_input.setStyleSheet(
            f"background-color: {tokens.BG_SURFACE};"
            f"color: {tokens.TEXT_PRIMARY};"
            f"border: 1px solid {tokens.BORDER};"
            f"border-radius: {tokens.RADIUS}px;"
            f"padding: 4px {tokens.SPACE_SM}px;"
        )
        desc_layout.addWidget(lbl_desc)
        desc_layout.addWidget(self._desc_input)
        layout.addLayout(desc_layout)

        layout.addStretch(1)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        self._btn_cancel = QPushButton("Cancel", self)
        self._btn_cancel.setObjectName("btnCancelRule")
        self._btn_cancel.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px;"
            f"}}"
        )
        self._btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_cancel)

        self._btn_save = QPushButton("Save Rule", self)
        self._btn_save.setObjectName("btnSaveRule")
        self._btn_save.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.ACCENT_PRIMARY};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 6px {tokens.SPACE_LG}px;"
            f"  font-weight: 600;"
            f"}}"
        )
        self._btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(self._btn_save)

        layout.addLayout(btn_layout)

    def get_rule_spec(self) -> RuleSpec:
        """Construct validated RuleSpec from dialog inputs."""
        rid = self._id_input.text().strip() or "rule_1"
        ev = self._event_combo.currentText()
        src = self._source_combo.currentData()

        eff_type = self._effect_type_combo.currentText()
        if eff_type == "End Game (Win)":
            effect = EndGame(kind="end_game", outcome="win")
        elif eff_type == "End Game (Lose)":
            effect = EndGame(kind="end_game", outcome="lose")
        else:
            effect = AddStat(kind="add_stat", stat="game.score", delta=float(self._delta_spin.value()))

        desc = self._desc_input.text().strip()
        existing_conds = self._rule.conditions if self._rule and hasattr(self._rule, "conditions") else []
        return RuleSpec(
            rule_id=rid,
            when=EventRef(event=ev, source=src),
            conditions=existing_conds,
            effects=[effect],
            description=desc,
        )
