"""Interactive Plan Artifact Card for GameForge IDE Chat.

Renders structured technical execution plans (PlanArtifact) inline in the chat:
- Goal, version, and status indicators
- Approach summary and implementation method
- Step checklist with real-time status markers (pending, in_progress, completed, failed, skipped)
- Prominent Proceed button to start execution of the approved plan
- Inline revision input for multi-turn plan refinement without modal dialogs
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Union

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from ..styles.dark_theme import theme_color


STEP_STATUS_ICONS = {
    "completed": ("✓", tokens.ACCENT_SUCCESS, "#052e16"),
    "in_progress": ("●", tokens.ACCENT_HOVER, "#1e1b4b"),
    "failed": ("✗", tokens.ACCENT_ERROR, "#450a0a"),
    "skipped": ("↷", tokens.TEXT_MUTED, "#18181b"),
    "pending": ("○", tokens.TEXT_SECONDARY, "#18181b"),
}


class PlanCard(QFrame):
    """Clean, interactive card rendering a structured PlanArtifact in chat."""

    proceed_clicked = Signal(str)            # plan_id
    revision_requested = Signal(str, str)     # (plan_id, revision_prompt)

    def __init__(self, plan_data: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("planCard")
        self.setAccessibleName("Execution Plan Card")

        self.plan_id: str = plan_data.get("plan_id", f"plan_{int(time.time())}")
        self.version: int = int(plan_data.get("version", 1))
        self.goal: str = plan_data.get("goal", "Execution Plan")
        self.summary: str = plan_data.get("summary", "")
        self.status: str = plan_data.get("status", "awaiting_approval")
        self.method: str = plan_data.get("implementation_method", "direct_code_edit")
        self.steps: List[Dict[str, Any]] = list(plan_data.get("steps", []))
        self.revisions: List[Any] = list(plan_data.get("revisions", []))

        self._step_widgets: Dict[str, QFrame] = {}
        self._build_ui()
        self.update_plan(plan_data)

    def _build_ui(self) -> None:
        accent = theme_color(tokens.ACCENT_PRIMARY)
        bg = theme_color(tokens.BG_PANEL)
        border_col = theme_color(tokens.BORDER)

        self.setStyleSheet(f"""
            QFrame#planCard {{
                background-color: {bg};
                border: 1px solid {accent};
                border-left: 4px solid {accent};
                border-radius: {tokens.RADIUS}px;
                margin: 6px 8px;
            }}
            QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # ── Header Row: Title, Version, Status ────────────────────────────
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self._lbl_icon = QLabel("📋", self)
        self._lbl_icon.setStyleSheet("font-size: 15px;")
        header_row.addWidget(self._lbl_icon)

        self._lbl_title = QLabel(f"Plan: {self.goal}", self)
        self._lbl_title.setObjectName("planCardTitle")
        self._lbl_title.setStyleSheet(f"""
            color: {tokens.TEXT_PRIMARY};
            font-size: 14px;
            font-weight: 700;
        """)
        self._lbl_title.setWordWrap(True)
        header_row.addWidget(self._lbl_title, 1)

        self._lbl_version = QLabel(f"v{self.version}", self)
        self._lbl_version.setObjectName("planCardVersion")
        self._lbl_version.setStyleSheet(f"""
            background-color: #312e81;
            color: #c7d2fe;
            border-radius: 4px;
            padding: 2px 7px;
            font-size: 11px;
            font-weight: 700;
        """)
        header_row.addWidget(self._lbl_version)

        self._lbl_progress = QLabel("", self)
        self._lbl_progress.setObjectName("planCardProgress")
        self._lbl_progress.setStyleSheet(f"""
            background-color: #064e3b;
            color: #6ee7b7;
            border-radius: 4px;
            padding: 2px 7px;
            font-size: 11px;
            font-weight: 700;
        """)
        self._lbl_progress.setVisible(False)
        header_row.addWidget(self._lbl_progress)

        self._lbl_status = QLabel(self.status.replace("_", " ").upper(), self)
        self._lbl_status.setObjectName("planCardStatus")
        self._lbl_status.setStyleSheet(f"""
            background-color: #1e1b4b;
            color: #a5b4fc;
            border: 1px solid #4338ca;
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 600;
        """)
        header_row.addWidget(self._lbl_status)
        layout.addLayout(header_row)

        # ── Meta / Approach summary ──────────────────────────────────────
        self._lbl_summary = QLabel(self.summary, self)
        self._lbl_summary.setObjectName("planCardSummary")
        self._lbl_summary.setWordWrap(True)
        self._lbl_summary.setStyleSheet(f"""
            color: {tokens.TEXT_SECONDARY};
            font-size: 12px;
            line-height: 1.4;
        """)
        layout.addWidget(self._lbl_summary)

        # Method indicator chip
        method_row = QHBoxLayout()
        method_row.setContentsMargins(0, 0, 0, 0)
        method_row.setSpacing(6)

        self._lbl_method = QLabel(f"Approach: {self.method.replace('_', ' ').title()}", self)
        self._lbl_method.setObjectName("planCardMethod")
        self._lbl_method.setStyleSheet(f"""
            color: {tokens.ACCENT_HOVER};
            font-size: 11px;
            font-weight: 600;
        """)
        method_row.addWidget(self._lbl_method)
        method_row.addStretch(1)

        self._lbl_plan_id = QLabel(f"ID: {self.plan_id}", self)
        self._lbl_plan_id.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: 10px;")
        method_row.addWidget(self._lbl_plan_id)
        layout.addLayout(method_row)

        # ── Step Checklist Container ─────────────────────────────────────
        self._steps_container = QWidget(self)
        self._steps_container.setObjectName("planStepsContainer")
        self._steps_layout = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(0, 4, 0, 4)
        self._steps_layout.setSpacing(6)
        layout.addWidget(self._steps_container)

        # ── Action Row (Proceed & Revise) ────────────────────────────────
        self._action_frame = QFrame(self)
        self._action_frame.setObjectName("planActionFrame")
        self._action_frame.setStyleSheet(f"""
            QFrame#planActionFrame {{
                background-color: {tokens.BG_SURFACE};
                border: 1px solid {tokens.BORDER};
                border-radius: 6px;
                padding: 6px;
            }}
        """)
        action_layout = QVBoxLayout(self._action_frame)
        action_layout.setContentsMargins(8, 8, 8, 8)
        action_layout.setSpacing(8)

        # Row with Proceed button
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(10)

        self.btn_proceed = QPushButton("▶ Proceed", self._action_frame)
        self.btn_proceed.setObjectName("btn_proceed")
        self.btnProceed = self.btn_proceed  # alias for tests
        self.btn_proceed.setAccessibleName("Proceed with plan execution")
        self.btn_proceed.setCursor(Qt.PointingHandCursor)
        self.btn_proceed.setStyleSheet(f"""
            QPushButton#btn_proceed {{
                background-color: {tokens.ACCENT_PRIMARY};
                color: {tokens.TEXT_PRIMARY};
                border: none;
                border-radius: {tokens.RADIUS}px;
                padding: 7px 22px;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }}
            QPushButton#btn_proceed:hover {{
                background-color: {tokens.ACCENT_HOVER};
            }}
            QPushButton#btn_proceed:pressed {{
                background-color: {tokens.ACCENT_ACTIVE};
            }}
            QPushButton#btn_proceed:disabled {{
                background-color: {tokens.BG_ROOT};
                color: {tokens.TEXT_MUTED};
                border: 1px solid {tokens.BORDER};
            }}
        """)
        self.btn_proceed.clicked.connect(self._on_proceed_clicked)
        btn_row.addWidget(self.btn_proceed)

        self._lbl_hint = QLabel("Click Proceed to execute, or refine requirements below:", self._action_frame)
        self._lbl_hint.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: 11px;")
        btn_row.addWidget(self._lbl_hint, 1)
        action_layout.addLayout(btn_row)

        # Inline Revision Input Row
        rev_row = QHBoxLayout()
        rev_row.setContentsMargins(0, 0, 0, 0)
        rev_row.setSpacing(6)

        self.txt_revision = QLineEdit(self._action_frame)
        self.txt_revision.setObjectName("planRevisionInput")
        self.revision_input = self.txt_revision  # alias
        self.txt_revision.setPlaceholderText("Refine plan (e.g. 'Use C++ instead of Blueprint', 'Add double jump')…")
        self.txt_revision.setStyleSheet(f"""
            QLineEdit#planRevisionInput {{
                background-color: {tokens.BG_ROOT};
                color: {tokens.TEXT_PRIMARY};
                border: 1px solid {tokens.BORDER};
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 12px;
            }}
            QLineEdit#planRevisionInput:focus {{
                border: 1px solid {tokens.BORDER_FOCUS};
            }}
        """)
        self.txt_revision.returnPressed.connect(self._on_revise_clicked)
        rev_row.addWidget(self.txt_revision, 1)

        self.btn_revise = QPushButton("Revise Plan", self._action_frame)
        self.btn_revise.setObjectName("btn_revise_plan")
        self.btnRevise = self.btn_revise  # alias
        self.btn_revise.setCursor(Qt.PointingHandCursor)
        self.btn_revise.setStyleSheet(f"""
            QPushButton#btn_revise_plan {{
                background-color: {tokens.BG_ROOT};
                color: {tokens.TEXT_PRIMARY};
                border: 1px solid {tokens.BORDER};
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#btn_revise_plan:hover {{
                background-color: {tokens.BG_HOVER};
                border-color: {tokens.ACCENT_PRIMARY};
            }}
        """)
        self.btn_revise.clicked.connect(self._on_revise_clicked)
        rev_row.addWidget(self.btn_revise)
        action_layout.addLayout(rev_row)

        layout.addWidget(self._action_frame)

    def _render_steps(self) -> None:
        """Render or update all steps in the plan checklist."""
        # Clear existing step widgets
        while self._steps_layout.count() > 0:
            item = self._steps_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._step_widgets.clear()

        if not self.steps:
            lbl_empty = QLabel("No steps defined in this plan.", self._steps_container)
            lbl_empty.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-style: italic;")
            self._steps_layout.addWidget(lbl_empty)
            return

        for idx, step in enumerate(self.steps, 1):
            s_id = step.get("step_id", f"step_{idx}")
            s_title = step.get("title", f"Step {idx}")
            s_desc = step.get("description", "")
            s_status = step.get("status", "pending")
            s_files = step.get("target_files", [])
            s_tools = step.get("tools", [])
            s_verif = step.get("verification", "")

            step_frame = QFrame(self._steps_container)
            step_frame.setObjectName(f"planStep_{s_id}")
            step_frame.setStyleSheet(f"""
                QFrame#planStep_{s_id} {{
                    background-color: {tokens.BG_SURFACE};
                    border: 1px solid {tokens.BORDER};
                    border-radius: 4px;
                    padding: 6px 8px;
                }}
            """)
            s_layout = QVBoxLayout(step_frame)
            s_layout.setContentsMargins(6, 6, 6, 6)
            s_layout.setSpacing(4)

            # Top row: icon, index, title, status tag
            top_h = QHBoxLayout()
            top_h.setContentsMargins(0, 0, 0, 0)
            top_h.setSpacing(6)

            icon_char, icon_col, icon_bg = STEP_STATUS_ICONS.get(s_status, ("○", tokens.TEXT_SECONDARY, "#18181b"))
            lbl_st_icon = QLabel(icon_char, step_frame)
            lbl_st_icon.setObjectName(f"stepStatus_{s_id}")
            lbl_st_icon.setStyleSheet(f"""
                color: {icon_col};
                background: {icon_bg};
                border-radius: 3px;
                padding: 1px 4px;
                font-weight: bold;
                font-size: 11px;
            """)
            top_h.addWidget(lbl_st_icon)

            lbl_step_num = QLabel(f"{idx}.", step_frame)
            lbl_step_num.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-weight: bold; font-size: 12px;")
            top_h.addWidget(lbl_step_num)

            lbl_st_title = QLabel(s_title, step_frame)
            lbl_st_title.setObjectName(f"stepTitle_{s_id}")
            lbl_st_title.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
            lbl_st_title.setWordWrap(True)
            top_h.addWidget(lbl_st_title, 1)

            lbl_st_badge = QLabel(s_status.replace("_", " "), step_frame)
            lbl_st_badge.setObjectName(f"stepBadge_{s_id}")
            lbl_st_badge.setStyleSheet(f"color: {icon_col}; font-size: 10px; font-weight: bold;")
            top_h.addWidget(lbl_st_badge)
            s_layout.addLayout(top_h)

            # Description
            if s_desc:
                lbl_desc = QLabel(s_desc, step_frame)
                lbl_desc.setWordWrap(True)
                lbl_desc.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: 11px;")
                s_layout.addWidget(lbl_desc)

            # Files / Verification
            meta_items = []
            if s_files:
                meta_items.append(f"📁 {', '.join(s_files)}")
            if s_tools:
                meta_items.append(f"🔧 {', '.join(s_tools)}")
            if s_verif:
                meta_items.append(f"✓ {s_verif}")
            if meta_items:
                lbl_meta = QLabel("  |  ".join(meta_items), step_frame)
                lbl_meta.setWordWrap(True)
                lbl_meta.setStyleSheet(f"color: {tokens.TEXT_MUTED}; font-size: 10px;")
                s_layout.addWidget(lbl_meta)

            # Output summary or error if present
            s_out = step.get("output_summary")
            if s_out:
                lbl_out = QLabel(f"✓ {s_out}", step_frame)
                lbl_out.setObjectName(f"stepOutput_{s_id}")
                lbl_out.setStyleSheet(f"color: {tokens.ACCENT_SUCCESS}; font-size: 11px; font-weight: 500;")
                s_layout.addWidget(lbl_out)
            s_err = step.get("error")
            if s_err:
                lbl_err = QLabel(f"✗ {s_err}", step_frame)
                lbl_err.setObjectName(f"stepError_{s_id}")
                lbl_err.setStyleSheet(f"color: {tokens.ACCENT_ERROR}; font-size: 11px; font-weight: 600;")
                s_layout.addWidget(lbl_err)

            self._steps_layout.addWidget(step_frame)
            self._step_widgets[s_id] = step_frame

        self._update_progress()

    def _update_progress(self) -> None:
        """Update live execution progress indicators across the plan steps."""
        total = len(self.steps)
        if total == 0:
            self._lbl_progress.setVisible(False)
            return
        completed = sum(1 for s in self.steps if s.get("status") == "completed")
        pct = int((completed / total) * 100)
        self._lbl_progress.setText(f"{completed}/{total} steps ({pct}%)")
        self._lbl_progress.setVisible(True)

    def update_plan(self, plan_data: Dict[str, Any]) -> None:
        """Update plan fields and step checklist in place."""
        self.plan_id = plan_data.get("plan_id", self.plan_id)
        self.version = int(plan_data.get("version", self.version))
        self.goal = plan_data.get("goal", self.goal)
        self.summary = plan_data.get("summary", self.summary)
        self.status = plan_data.get("status", self.status)
        self.method = plan_data.get("implementation_method", self.method)
        self.steps = list(plan_data.get("steps", self.steps))
        self.revisions = list(plan_data.get("revisions", self.revisions))
        proceed_confirmed = bool(plan_data.get("proceed_confirmed", False))

        self._lbl_title.setText(f"Plan: {self.goal}")
        self._lbl_version.setText(f"v{self.version}")
        self._lbl_status.setText(self.status.replace("_", " ").upper())
        self._lbl_summary.setText(self.summary)
        self._lbl_method.setText(f"Approach: {self.method.replace('_', ' ').title()}")
        self._lbl_plan_id.setText(f"ID: {self.plan_id}")

        self._render_steps()

        if proceed_confirmed or self.status in ("approved", "executing"):
            self.btn_proceed.setText("✓ Approved & Executing")
            self.btn_proceed.setEnabled(False)
            self._lbl_hint.setText("Plan approved. Execution running in assistant.")
            self.txt_revision.setEnabled(False)
            self.btn_revise.setEnabled(False)
        elif self.status == "completed":
            self.btn_proceed.setText("✓ Plan Completed")
            self.btn_proceed.setEnabled(False)
            self._lbl_hint.setText("All plan steps completed successfully.")
            self.txt_revision.setEnabled(False)
            self.btn_revise.setEnabled(False)
        else:
            self.btn_proceed.setText("▶ Proceed")
            self.btn_proceed.setEnabled(True)
            self.txt_revision.setEnabled(True)
            self.btn_revise.setEnabled(True)

    def update_step(self, step_id: str, status: str, output_summary: str = "", error: str = "") -> None:
        """Update a single step status, icon, badge, and metadata in place."""
        for step in self.steps:
            if step.get("step_id") == step_id:
                step["status"] = status
                if output_summary:
                    step["output_summary"] = output_summary
                if error:
                    step["error"] = error
                break

        icon_char, icon_col, icon_bg = STEP_STATUS_ICONS.get(status, ("○", tokens.TEXT_SECONDARY, "#18181b"))
        step_frame = self._step_widgets.get(step_id)
        if step_frame:
            lbl_icon = step_frame.findChild(QLabel, f"stepStatus_{step_id}")
            if lbl_icon:
                lbl_icon.setText(icon_char)
                lbl_icon.setStyleSheet(f"""
                    color: {icon_col};
                    background: {icon_bg};
                    border-radius: 3px;
                    padding: 1px 4px;
                    font-weight: bold;
                    font-size: 11px;
                """)
            lbl_badge = step_frame.findChild(QLabel, f"stepBadge_{step_id}")
            if lbl_badge:
                lbl_badge.setText(status.replace("_", " "))
                lbl_badge.setStyleSheet(f"color: {icon_col}; font-size: 10px; font-weight: bold;")

            if output_summary:
                lbl_out = step_frame.findChild(QLabel, f"stepOutput_{step_id}")
                if lbl_out:
                    lbl_out.setText(f"✓ {output_summary}")
                    lbl_out.setVisible(True)
                else:
                    lbl_out = QLabel(f"✓ {output_summary}", step_frame)
                    lbl_out.setObjectName(f"stepOutput_{step_id}")
                    lbl_out.setStyleSheet(f"color: {tokens.ACCENT_SUCCESS}; font-size: 11px; font-weight: 500;")
                    step_frame.layout().addWidget(lbl_out)

            if error:
                lbl_err = step_frame.findChild(QLabel, f"stepError_{step_id}")
                if lbl_err:
                    lbl_err.setText(f"✗ {error}")
                    lbl_err.setVisible(True)
                else:
                    lbl_err = QLabel(f"✗ {error}", step_frame)
                    lbl_err.setObjectName(f"stepError_{step_id}")
                    lbl_err.setStyleSheet(f"color: {tokens.ACCENT_ERROR}; font-size: 11px; font-weight: 600;")
                    step_frame.layout().addWidget(lbl_err)

        self._update_progress()

    def _on_proceed_clicked(self) -> None:
        self.btn_proceed.setEnabled(False)
        self.btn_proceed.setText("Executing…")
        self.status = "approved"
        self._lbl_status.setText("APPROVED")
        self.proceed_clicked.emit(self.plan_id)

    def _on_revise_clicked(self) -> None:
        text = self.txt_revision.text().strip()
        if not text:
            return
        self.txt_revision.clear()
        self.revision_requested.emit(self.plan_id, text)
