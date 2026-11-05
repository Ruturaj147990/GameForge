"""Inline approval card for long-running, approval-gated actions (e.g. create_game).

States: PENDING (Approve / Reject) -> RUNNING (live stage checklist) -> DONE / FAILED
(result summary with Play, Open folder and Report buttons).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...pipeline.game_pipeline import STAGES
from ..styles.dark_theme import theme_color

STAGE_LABELS = {
    "spec": "Validate game spec and engine tools",
    "scaffold": "Create Unreal C++ project",
    "sources": "Generate gameplay source code",
    "build_editor": "Compile (UnrealBuildTool)",
    "assemble_level": "Build the level in Unreal Editor",
    "automation_tests": "Run automation tests",
    "package": "Cook and package for Windows",
    "packaged_smoke": "Play-test the packaged game",
    "design": "Design the game (model)",
    "framework": "Install the GameForge host framework",
    "author": "Write gameplay C++ (model) + safety scan",
    "build_repair": "Compile, repairing from compiler errors",
    "quality_review": "Vision review of gameplay (advisory) + improvement round",
    "content": "Prepare visual and audio assets",
    "codegen": "Generate gameplay source code",
    "automation": "Run automation tests",
    "scenarios": "Play-test packaged game scenarios",
    "scenario_gen": "Generate QA test scenarios",
    "review": "Vision and quality review",
    "report": "Compile build and test evidence report",
}


class ApprovalCard(QFrame):
    approve_clicked = Signal(str)
    reject_clicked = Signal(str)
    play_clicked = Signal(str)
    cancel_clicked = Signal(str)

    def __init__(self, approval: Dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.approval_id = approval["approval_id"]
        self._exe: Optional[str] = None
        self._stage_labels: Dict[str, QLabel] = {}
        self.setObjectName("approvalCard")
        accent = theme_color("#7c3aed")
        self.setStyleSheet(
            f"#approvalCard {{ border: 1px solid {accent}; border-radius: 6px; "
            f"background: {theme_color('#120f1d')}; }} QLabel {{ background: transparent; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        title = QLabel(f"<b>Approval required — {approval.get('tool', 'action').replace('_', ' ')}</b>")
        title.setTextFormat(Qt.RichText)
        lay.addWidget(title)
        summary = QLabel(approval.get("summary", ""))
        summary.setWordWrap(True)
        lay.addWidget(summary)
        consequence = QLabel(f"<i>{approval.get('consequence', '')}</i>")
        consequence.setWordWrap(True)
        consequence.setTextFormat(Qt.RichText)
        lay.addWidget(consequence)
        self._consequence = consequence

        # Authoritative Project Root row (Two-Location Storage Architecture)
        args = approval.get("args", {})
        proj_dir = args.get("project_dir") or args.get("project_root")
        if not proj_dir and approval.get("tool") in ("create_game", "create_game_freeform"):
            from ...core.settings import get_settings
            from ...core.projects import resolve_project_dir
            proj_name = args.get("project_name") or args.get("title") or "MyGame"
            proj_dir = resolve_project_dir(proj_name) or (get_settings().projects_root / proj_name)
            args["project_dir"] = str(proj_dir)

        if proj_dir:
            dir_row = QHBoxLayout()
            self._lbl_card_dir = QLabel(f"<b>Project Root:</b> <code>{proj_dir}</code>")
            self._lbl_card_dir.setTextFormat(Qt.RichText)
            self._lbl_card_dir.setStyleSheet("color: #cbd5e1; font-size: 11px;")
            dir_row.addWidget(self._lbl_card_dir, 1)
            lay.addLayout(dir_row)

        scope = approval.get("args", {}).get("scope") or approval.get("scope")
        if isinstance(scope, dict):
            scope_lines = []
            if "paths" in scope:
                scope_lines.append(f"<b>Paths:</b> <code>{scope['paths']}</code>")
            if "engine" in scope:
                scope_lines.append(f"<b>Engine:</b> {scope['engine']}")
            if "packaging" in scope:
                scope_lines.append(f"<b>Packaging:</b> {'Yes' if scope['packaging'] else 'No'}")
            if "estimated_minutes" in scope:
                scope_lines.append(f"<b>Estimated time:</b> ~{scope['estimated_minutes']} min")
            if scope_lines:
                scope_lbl = QLabel("<br>".join(scope_lines))
                scope_lbl.setTextFormat(Qt.RichText)
                scope_lbl.setStyleSheet("color: #cbd5e1; font-size: 11px;")
                lay.addWidget(scope_lbl)

        summary_md = approval.get("summary_md", "")
        if summary_md:
            self._spec_toggle = QPushButton("▶  Show Game Design Spec")
            self._spec_toggle.setFlat(True)
            self._spec_toggle.setCursor(Qt.PointingHandCursor)
            self._spec_toggle.setStyleSheet("text-align: left; padding: 2px 0; color: #a78bfa; font-weight: bold;")
            lay.addWidget(self._spec_toggle)

            self._spec_content = QLabel(summary_md)
            self._spec_content.setWordWrap(True)
            self._spec_content.setTextFormat(Qt.MarkdownText)
            self._spec_content.setVisible(False)
            lay.addWidget(self._spec_content)

            def toggle_spec():
                is_vis = not self._spec_content.isVisible()
                self._spec_content.setVisible(is_vis)
                self._spec_toggle.setText("▼  Hide Game Design Spec" if is_vis else "▶  Show Game Design Spec")

            self._spec_toggle.clicked.connect(toggle_spec)
        self._elapsed = QLabel("")
        self._elapsed.setVisible(False)
        lay.addWidget(self._elapsed)
        self._started = 0.0
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._update_elapsed)

        self._stage_box = QWidget()
        sb = QVBoxLayout(self._stage_box)
        sb.setContentsMargins(4, 4, 4, 4)
        sb.setSpacing(2)
        for st in approval.get("stages") or STAGES:
            if st in STAGE_LABELS:
                lbl = QLabel(f"○  {STAGE_LABELS[st]}")
                self._stage_labels[st] = lbl
                sb.addWidget(lbl)
        self._stage_box.setVisible(False)
        lay.addWidget(self._stage_box)

        self._result = QLabel("")
        self._result.setWordWrap(True)
        self._result.setTextFormat(Qt.RichText)
        self._result.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._result.setOpenExternalLinks(True)
        self._result.setVisible(False)
        lay.addWidget(self._result)

        row = QHBoxLayout()
        self._btn_approve = QPushButton("Approve and build")
        self._btn_approve.setObjectName("approvalApprove")
        self._btn_reject = QPushButton("Reject")
        self._btn_reject.setObjectName("approvalReject")
        self._btn_play = QPushButton("▶  Play game")
        self._btn_play.setObjectName("approvalPlay")
        self._btn_folder = QPushButton("Open folder")
        self._btn_cancel = QPushButton("Cancel build")
        self._btn_cancel.setObjectName("approvalCancel")
        self._btn_cancel.setVisible(False)
        self._btn_play.setVisible(False)
        self._btn_folder.setVisible(False)
        for b in (self._btn_approve, self._btn_reject, self._btn_cancel, self._btn_play, self._btn_folder):
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        self._btn_approve.clicked.connect(self._on_approve)
        self._btn_reject.clicked.connect(self._on_reject)
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_play.clicked.connect(lambda: self._exe and self.play_clicked.emit(self._exe))
        self._project_dir: Optional[str] = None
        self._btn_folder.clicked.connect(self._open_folder)

    # ── state transitions ──────────────────────────────────────────────────
    def _on_approve(self) -> None:
        self._btn_approve.setEnabled(False)  # idempotent: one click, one run
        self._btn_reject.setEnabled(False)
        self.approve_clicked.emit(self.approval_id)

    def _on_reject(self) -> None:
        self._btn_approve.setEnabled(False)
        self._btn_reject.setEnabled(False)
        self.reject_clicked.emit(self.approval_id)
        self._show_result("<b>Rejected.</b> Nothing was changed.")

    def _on_cancel(self) -> None:
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.setText("Cancelling…")
        self.cancel_clicked.emit(self.approval_id)

    def set_running(self) -> None:
        self._btn_approve.setVisible(False)
        self._btn_reject.setVisible(False)
        self._btn_cancel.setVisible(True)
        self._consequence.setVisible(False)  # collapse once running
        self._started = time.monotonic()
        self._elapsed.setVisible(True)
        self._update_elapsed()
        self._tick.start()
        self._stage_box.setVisible(True)

    def on_progress(self, kind: str, data: Dict) -> None:
        stage = data.get("stage")
        lbl = self._stage_labels.get(stage)
        if not lbl and stage and stage.startswith("assemble_"):
            lbl = self._stage_labels.get("assemble_level")
        if not lbl and "step_id" in data:
            sid = data["step_id"]
            lbl = self._stage_labels.get(sid)
            if not lbl and sid.startswith("assemble_"):
                lbl = self._stage_labels.get("assemble_level")
        if not lbl:
            return
        text = STAGE_LABELS.get(stage) or STAGE_LABELS.get(data.get("step_id", "")) or stage
        if kind == "stage_started":
            lbl.setText(f"◐  {text} …")
        elif kind == "build_attempt" and not data.get("ok"):
            lbl = self._stage_labels.get("build_repair")
            if lbl:
                lbl.setText(f"◐  {STAGE_LABELS['build_repair']} … attempt {data.get('attempt', 0) + 1}: "
                            f"{data.get('errors')} error(s), asking the model to fix")
            return
        elif kind == "stage_finished":
            mark = "✔" if data.get("ok") else "✖"
            dur = data.get("duration_s")
            extra = "" if data.get("ok") else f" — {'; '.join(data.get('errors') or [])[:160]}"
            lbl.setText(f"{mark}  {text} ({dur}s){extra}")

    def _update_elapsed(self, final: bool = False) -> None:
        secs = int(time.monotonic() - self._started) if self._started else 0
        label = "Finished in" if final else "Running for"
        self._elapsed.setText(f"{label} {secs // 60}:{secs % 60:02d}")

    def on_finished(self, result: Dict) -> None:
        self._stage_box.setVisible(True)
        self._btn_cancel.setVisible(False)
        self._tick.stop()
        if self._started:
            self._update_elapsed(final=True)
        self._project_dir = result.get("project_dir")
        if result.get("status") == "SUCCESS":
            self._exe = result.get("exe")
            report = result.get("report_path", "")
            html = "<b>✔ Done — all acceptance checks passed.</b>"
            if self._exe:
                html += f"<br>Game: <code>{self._exe}</code>"
            if report:
                html += f"<br>Evidence: <a href='file:///{report.replace(os.sep, '/')}'>pipeline report</a>"
            self._show_result(html)
            self._btn_play.setVisible(bool(self._exe))
        else:
            err = result.get("error") or f"failed at stage {result.get('failed_stage')}"
            self._show_result(f"<b>✖ Not complete:</b> {err}")
        self._btn_folder.setVisible(bool(self._project_dir))

    def show_already_handled(self, status: str) -> None:
        self._btn_approve.setVisible(False)
        self._btn_reject.setVisible(False)
        self._show_result(f"<b>{status}</b>")

    def _show_result(self, html: str) -> None:
        self._result.setText(html)
        self._result.setVisible(True)

    def _open_folder(self) -> None:
        if self._project_dir and Path(self._project_dir).is_dir():
            os.startfile(self._project_dir)  # noqa: S606 - opens Explorer on a GameForge-created folder
