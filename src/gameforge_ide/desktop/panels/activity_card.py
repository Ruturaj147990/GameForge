"""GameForge IDE — Background Activity & Tool Execution Items.

Provides Antigravity-style compact, high-contrast, real-time background activity
chips and tool execution pills in the chat panel with expandable details.
"""

from __future__ import annotations

import html
import json
import time
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from ..styles.dark_theme import theme_color, theme_stylesheet


def format_target_path(raw: str, max_parts: int = 3) -> str:
    """Format a file path into a concise, human-readable display string."""
    if not raw:
        return ""
    p = str(raw).replace("\\", "/").strip()
    # Normalize drive letters (e.g. E:/...)
    if len(p) >= 3 and p[1:3] == ":/":
        parts = [part for part in p.split("/") if part]
        if len(parts) > max_parts:
            return f".../{parts[-2]}/{parts[-1]}"
        return "/".join(parts)
    for prefix in ("./", "/"):
        if p.startswith(prefix):
            p = p[len(prefix):]
    parts = [part for part in p.split("/") if part]
    if len(parts) > max_parts:
        return f"{parts[0]}/.../{parts[-1]}"
    return "/".join(parts)


def format_tool_activity(
    tool_name: str,
    args: Dict[str, Any],
    result: Optional[Dict[str, Any]] = None,
    is_running: bool = False,
) -> Tuple[str, str, str, str]:
    """Format tool execution into (icon, action, target, badge).

    Examples:
        ("📖", "Read", "xyz.py", "42 lines")
        ("✏️", "Edit", "Source/Player.cpp", "+6 / -2 lines")
        ("⚡", "Ran", "pytest tests/unit", "exit 0")
    """
    args = args or {}
    status = (result.get("status") if isinstance(result, dict) else "") or ""
    is_error = status == "ERROR" or (isinstance(result, dict) and bool(result.get("error")))

    if tool_name == "read_file":
        path = args.get("subpath") or args.get("file_path") or args.get("path") or ""
        target = format_target_path(path) or "file"
        icon = "📖"
        action = "Reading" if is_running else ("Read failed" if is_error else "Read")
        badge = "..." if is_running else ""
        if result and not is_running:
            if is_error:
                badge = "failed"
            else:
                lines = result.get("lines")
                if lines is None and "content" in result:
                    lines = len(str(result["content"]).splitlines())
                badge = f"{lines} lines" if lines is not None else "ok"

    elif tool_name == "write_file":
        path = args.get("subpath") or args.get("file_path") or args.get("path") or ""
        target = format_target_path(path) or "file"
        icon = "📝"
        action = "Writing" if is_running else ("Write failed" if is_error else "Wrote")
        badge = "..." if is_running else ""
        if result and not is_running:
            if is_error:
                badge = "failed"
            else:
                content = args.get("content", "")
                lines = len(str(content).splitlines()) if content else 0
                badge = f"{lines} lines" if lines else "saved"

    elif tool_name == "propose_edit":
        path = args.get("subpath") or args.get("file_path") or args.get("path") or ""
        target = format_target_path(path) or "file"
        icon = "✏️"
        action = "Editing" if is_running else ("Edit failed" if is_error else "Edited")
        badge = "..." if is_running else ""
        if result and not is_running:
            if is_error:
                badge = "failed"
            else:
                patch = str(result.get("diff_patch", ""))
                if patch:
                    added = sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
                    removed = sum(1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
                    badge = f"+{added} / -{removed} lines"
                else:
                    badge = "diff ready"

    elif tool_name in ("apply_edit", "apply_diff"):
        target_path = args.get("file_path") or args.get("subpath") or args.get("diff_id") or ""
        target = format_target_path(target_path) or "changes"
        icon = "✅"
        action = "Applying edit" if is_running else ("Apply failed" if is_error else "Applied changes to")
        badge = "..." if is_running else ("failed" if is_error else "applied")

    elif tool_name in ("apply_batch", "apply_diffs_batch"):
        icon = "✅"
        action = "Applying batch" if is_running else ("Batch failed" if is_error else "Applied batch edits")
        count = len(result.get("files", [])) if (result and isinstance(result, dict)) else len(args.get("diff_ids", []))
        target = f"({count} files)" if count else "files"
        badge = "..." if is_running else ("failed" if is_error else "applied")

    elif tool_name in ("rollback_edit", "rollback_batch", "diff_rollback"):
        icon = "↩️"
        action = "Reverting" if is_running else ("Revert failed" if is_error else "Reverted")
        target = "changes"
        badge = "..." if is_running else ("failed" if is_error else "restored")

    elif tool_name == "search_code":
        query = args.get("query") or args.get("pattern") or ""
        target = f'"{query}"' if query else "codebase"
        icon = "🔍"
        action = "Searching code for" if is_running else ("Search failed" if is_error else "Searched code for")
        badge = "..." if is_running else ""
        if result and not is_running:
            if is_error:
                badge = "failed"
            else:
                matches = result.get("matches", []) or result.get("count", 0)
                count = len(matches) if isinstance(matches, list) else int(matches)
                badge = f"{count} match{'es' if count != 1 else ''}"

    elif tool_name == "search_index":
        query = args.get("query") or ""
        target = f'"{query}"' if query else "symbol index"
        icon = "🔎"
        action = "Searching symbols for" if is_running else ("Search failed" if is_error else "Searched symbols for")
        badge = "..." if is_running else ""
        if result and not is_running:
            if is_error:
                badge = "failed"
            else:
                symbols = result.get("results", []) or result.get("count", 0)
                count = len(symbols) if isinstance(symbols, list) else int(symbols)
                badge = f"{count} symbol{'s' if count != 1 else ''}"

    elif tool_name == "list_dir":
        path = args.get("subpath") or args.get("path") or "."
        target = format_target_path(path) or "."
        icon = "📁"
        action = "Listing" if is_running else ("List failed" if is_error else "Listed")
        badge = "..." if is_running else ""
        if result and not is_running:
            if is_error:
                badge = "failed"
            else:
                entries = result.get("items") or result.get("entries") or result.get("files") or []
                count = result.get("count") if ("count" in result and isinstance(result["count"], int)) else (len(entries) if isinstance(entries, list) else 0)
                badge = f"{count} item{'s' if count != 1 else ''}"

    elif tool_name in ("run_command", "terminal_run"):
        cmd = str(args.get("command") or args.get("cmd") or "").strip()
        short_cmd = (cmd[:45] + "...") if len(cmd) > 45 else cmd
        target = short_cmd or "command"
        icon = "⚡"
        action = "Running" if is_running else ("Command failed" if is_error else "Ran")
        badge = "..." if is_running else ""
        if result and not is_running:
            code = result.get("exit_code", result.get("returncode", 0))
            badge = f"exit {code}"

    elif tool_name == "unreal_run_tests":
        target = "Unreal automation tests"
        icon = "🧪"
        action = "Running" if is_running else ("Tests failed" if is_error else "Ran")
        badge = "..." if is_running else ("failed" if is_error else "passed")

    elif tool_name == "unreal_package":
        target = "game executable"
        icon = "📦"
        action = "Packaging" if is_running else ("Packaging failed" if is_error else "Packaged")
        badge = "..." if is_running else ("failed" if is_error else "ready")

    elif tool_name == "unreal_build":
        target = str(args.get("project_name") or "Unreal project")
        icon = "🔨"
        action = "Building" if is_running else ("Build failed" if is_error else "Built")
        badge = "..." if is_running else ("failed" if is_error else "done")

    elif tool_name == "unreal_editor":
        op = str(args.get("op", "operation"))
        target = op
        icon = "🎮"
        action = "Unreal Editor"
        badge = "..." if is_running else ("failed" if is_error else "ok")

    elif tool_name in ("create_game", "create_game_freeform"):
        prompt = str(args.get("prompt", "game assets"))
        short_prompt = (prompt[:35] + "...") if len(prompt) > 35 else prompt
        target = short_prompt
        icon = "🎮"
        action = "Forge pipeline"
        badge = "..." if is_running else ("failed" if is_error else "done")

    elif tool_name == "verify_disk":
        path = args.get("subpath") or args.get("file_path") or ""
        target = format_target_path(path) or "file"
        icon = "🔍"
        action = "Verifying" if is_running else ("Verify failed" if is_error else "Verified")
        badge = "..." if is_running else ("failed" if is_error else "verified on disk")

    elif tool_name in ("git_status", "git_diff"):
        target = tool_name.replace("_", " ")
        icon = "🌿"
        action = "Checking" if is_running else "Checked"
        badge = "..." if is_running else "ok"

    else:
        target = tool_name
        icon = "🔧"
        action = "Running" if is_running else ("Failed" if is_error else "Ran")
        badge = "..." if is_running else ("failed" if is_error else "ok")

    return icon, action, target, badge


class ToolActivityItem(QFrame):
    """Sleek, high-contrast inline activity pill representing a background tool execution."""

    def __init__(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.role = "tool"
        self.tool_name = tool_name
        self.args = args or {}
        self.result = result
        self.is_running = result is None
        self._start_time = time.time()
        self._elapsed_s = 0.0

        self.setObjectName("toolActivityItem")
        self.setAccessibleName(f"Tool execution activity: {tool_name}")

        self._apply_frame_style()

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(10, 6, 10, 6)
        self._main_layout.setSpacing(4)

        # Header row
        self._header = QHBoxLayout()
        self._header.setContentsMargins(0, 0, 0, 0)
        self._header.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setStyleSheet("font-size: 13px; background: transparent; border: none;")
        self._header.addWidget(self._icon_label)

        self._title_label = QLabel()
        self._title_label.setStyleSheet("background: transparent; border: none;")
        self._header.addWidget(self._title_label)

        self._badge_label = QLabel()
        self._badge_label.setStyleSheet("background: transparent; border: none;")
        self._header.addWidget(self._badge_label)

        self._header.addStretch()

        self._btn_toggle = QPushButton("▸ Details")
        self._btn_toggle.setObjectName("btnToggleDetails")
        self._btn_toggle.setAccessibleName("Toggle tool details")
        self._btn_toggle.setToolTip("Click to inspect tool arguments and output")
        self._btn_toggle.setCursor(Qt.PointingHandCursor)
        self._btn_toggle.setStyleSheet(theme_stylesheet(f"""
            QPushButton#btnToggleDetails {{
                background: {tokens.BG_ROOT};
                border: 1px solid {tokens.BORDER};
                border-radius: 4px;
                padding: 1px 7px;
                color: {tokens.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton#btnToggleDetails:hover {{
                border-color: {tokens.ACCENT_PRIMARY};
                color: {tokens.TEXT_PRIMARY};
                background: {tokens.BG_HOVER};
            }}
        """))
        self._btn_toggle.clicked.connect(self.toggle_details)
        self._header.addWidget(self._btn_toggle)

        self._main_layout.addLayout(self._header)

        # Collapsible details drawer (initially hidden)
        self._details_frame = QFrame()
        self._details_frame.setObjectName("detailsFrame")
        self._details_frame.setVisible(False)
        self._details_frame.setStyleSheet(theme_stylesheet(f"""
            QFrame#detailsFrame {{
                background-color: {tokens.BG_ROOT};
                border: 1px solid {tokens.BORDER};
                border-radius: 4px;
                margin-top: 4px;
                padding: 6px;
            }}
        """))
        details_layout = QVBoxLayout(self._details_frame)
        details_layout.setContentsMargins(6, 6, 6, 6)
        details_layout.setSpacing(6)

        # Arguments preview
        lbl_args = QLabel("ARGUMENTS:")
        lbl_args.setStyleSheet(f"color: {theme_color(tokens.TEXT_SECONDARY)}; font-size: 10px; font-weight: 700; background: transparent;")
        details_layout.addWidget(lbl_args)

        self._args_edit = QPlainTextEdit()
        self._args_edit.setReadOnly(True)
        self._args_edit.setMaximumHeight(120)
        self._args_edit.setStyleSheet(theme_stylesheet(f"""
            QPlainTextEdit {{
                background: {tokens.BG_PANEL};
                border: 1px solid {tokens.BORDER};
                border-radius: 4px;
                color: {tokens.TEXT_PRIMARY};
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 11px;
                padding: 4px;
            }}
        """))
        try:
            self._args_edit.setPlainText(json.dumps(self.args, indent=2))
        except Exception:
            self._args_edit.setPlainText(str(self.args))
        details_layout.addWidget(self._args_edit)

        # Result preview
        self._lbl_result = QLabel("RESULT:")
        self._lbl_result.setStyleSheet(f"color: {theme_color(tokens.TEXT_SECONDARY)}; font-size: 10px; font-weight: 700; background: transparent;")
        details_layout.addWidget(self._lbl_result)

        self._result_edit = QPlainTextEdit()
        self._result_edit.setReadOnly(True)
        self._result_edit.setMaximumHeight(160)
        self._result_edit.setStyleSheet(theme_stylesheet(f"""
            QPlainTextEdit {{
                background: {tokens.BG_PANEL};
                border: 1px solid {tokens.BORDER};
                border-radius: 4px;
                color: {tokens.TEXT_PRIMARY};
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 11px;
                padding: 4px;
            }}
        """))
        self._update_result_edit()
        details_layout.addWidget(self._result_edit)

        # Copy button in details
        self._btn_copy = QPushButton("Copy Arguments & Output")
        self._btn_copy.setObjectName("btnCopyDetails")
        self._btn_copy.setStyleSheet(theme_stylesheet(f"""
            QPushButton#btnCopyDetails {{
                background: {tokens.BG_SURFACE};
                border: 1px solid {tokens.BORDER};
                border-radius: 4px;
                padding: 2px 8px;
                color: {tokens.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton#btnCopyDetails:hover {{
                border-color: {tokens.ACCENT_PRIMARY};
                color: {tokens.TEXT_PRIMARY};
            }}
        """))
        self._btn_copy.clicked.connect(self._copy_details)
        details_layout.addWidget(self._btn_copy, 0, Qt.AlignRight)


        self._main_layout.addWidget(self._details_frame)

        self._details_expanded = False

        # Pulse timer for animated active states
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(600)
        self._pulse_tick = 0
        self._pulse_timer.timeout.connect(self._on_pulse)

        self._raw_text = ""
        self._refresh_display()

        if self.is_running:
            self._pulse_timer.start()

    def _apply_frame_style(self) -> None:
        bg = theme_color(tokens.BG_SURFACE)
        border = theme_color(tokens.BORDER)
        hover_bg = theme_color(tokens.BG_HOVER)
        accent = theme_color(tokens.ACCENT_PRIMARY)
        self.setStyleSheet(f"""
            QFrame#toolActivityItem {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {tokens.RADIUS}px;
                margin: 2px 10px;
            }}
            QFrame#toolActivityItem:hover {{
                background-color: {hover_bg};
                border-color: {accent};
            }}
        """)

    def _refresh_display(self) -> None:
        icon, action, target, badge = format_tool_activity(
            self.tool_name, self.args, self.result, is_running=self.is_running
        )
        self._icon_label.setText(icon)

        accent = theme_color(tokens.ACCENT_HOVER)
        text_primary = theme_color(tokens.TEXT_PRIMARY)
        text_sec = theme_color(tokens.TEXT_SECONDARY)
        accent_succ = theme_color(tokens.ACCENT_SUCCESS)
        accent_err = theme_color(tokens.ACCENT_ERROR)
        accent_warn = theme_color(tokens.ACCENT_WARNING)

        # Title
        action_html = html.escape(action)
        target_html = html.escape(target)
        self._title_label.setText(
            f'<span style="color: {accent}; font-weight: 600; font-size: 12px;">{action_html}</span> '
            f'<span style="color: {text_primary}; font-weight: 700; font-size: 12px;">{target_html}</span>'
        )

        # Badge
        if badge:
            badge_color = (
                accent_warn if self.is_running
                else (accent_err if "fail" in badge.lower() or "error" in badge.lower() else accent_succ)
            )
            self._badge_label.setText(
                f'<span style="color: {badge_color}; font-size: 11px; font-weight: 600;">({html.escape(badge)})</span>'
            )
        else:
            self._badge_label.setText("")

        self._raw_text = f"{icon} {action} {target} {badge}".strip()

    def _update_result_edit(self) -> None:
        if self.result is not None:
            try:
                self._result_edit.setPlainText(json.dumps(self.result, indent=2))
            except Exception:
                self._result_edit.setPlainText(str(self.result))
        else:
            self._result_edit.setPlainText("Running in background...")

    @Slot()
    def _on_pulse(self) -> None:
        if not self.is_running:
            self._pulse_timer.stop()
            return
        self._pulse_tick += 1
        dots = "." * ((self._pulse_tick % 3) + 1)
        accent_warn = theme_color(tokens.ACCENT_WARNING)
        self._badge_label.setText(
            f'<span style="color: {accent_warn}; font-size: 11px; font-weight: 600;">({dots})</span>'
        )

    def set_result(self, result: Dict[str, Any]) -> None:
        """Update this activity item with the tool's execution result in-place."""
        self.is_running = False
        if self._pulse_timer.isActive():
            self._pulse_timer.stop()
        self.result = result or {}
        self._elapsed_s = max(0.05, round(time.time() - self._start_time, 2))
        self._update_result_edit()
        self._refresh_display()

    @Slot()
    def toggle_details(self) -> None:
        """Expand or collapse the details drawer."""
        self._details_expanded = not getattr(self, "_details_expanded", False)
        self._details_frame.setVisible(self._details_expanded)
        self._btn_toggle.setText("▾ Details" if self._details_expanded else "▸ Details")

    @Slot()
    def _copy_details(self) -> None:
        payload = {
            "tool": self.tool_name,
            "arguments": self.args,
            "result": self.result,
            "elapsed_seconds": self._elapsed_s,
        }
        try:
            text = json.dumps(payload, indent=2)
        except Exception:
            text = str(payload)
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(text)
        if hasattr(self, "_btn_copy") and self._btn_copy is not None:
            self._btn_copy.setText("Copied! ✓")
            QTimer.singleShot(1500, lambda: self._btn_copy.setText("Copy Arguments & Output") if hasattr(self, "_btn_copy") and self._btn_copy and not self._btn_copy.isHidden() else None)


    def finalise(self) -> None:
        """Finalize activity item cleanly."""
        if self.is_running:
            self.set_result(self.result or {"status": "SUCCESS"})

    def has_tokens(self) -> bool:
        return bool(self._raw_text)

    def deleteLater(self) -> None:
        try:
            if hasattr(self, "_pulse_timer") and self._pulse_timer and self._pulse_timer.isActive():
                self._pulse_timer.stop()
        except Exception:
            pass
        super().deleteLater()


class StatusActivityItem(QFrame):
    """Sleek inline activity pill representing a background agent status (Thinking, Planning, Repairing)."""

    def __init__(
        self,
        status_kind: str,
        meta: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.role = "status"
        self.status_kind = status_kind.lower()
        self.meta = meta or {}
        self.is_running = True
        self._start_time = time.time()
        self._elapsed_s = 0.0

        self.setObjectName("statusActivityItem")
        self.setAccessibleName(f"Agent {status_kind} activity")

        self._apply_frame_style()

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 5, 10, 5)
        self._layout.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setStyleSheet("font-size: 13px; background: transparent; border: none;")
        self._layout.addWidget(self._icon_label)

        self._title_label = QLabel()
        self._title_label.setStyleSheet("background: transparent; border: none;")
        self._layout.addWidget(self._title_label)

        self._badge_label = QLabel()
        self._badge_label.setStyleSheet("background: transparent; border: none;")
        self._layout.addWidget(self._badge_label)

        self._layout.addStretch()

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(500)
        self._pulse_tick = 0
        self._pulse_timer.timeout.connect(self._on_pulse)

        self._raw_text = ""
        self._refresh_display()
        self._pulse_timer.start()

    def _apply_frame_style(self) -> None:
        bg = theme_color(tokens.BG_SURFACE)
        border = theme_color(tokens.BORDER)
        self.setStyleSheet(f"""
            QFrame#statusActivityItem {{
                background-color: {bg};
                border: 1px dashed {border};
                border-radius: {tokens.RADIUS}px;
                margin: 2px 10px;
            }}
        """)

    def _refresh_display(self) -> None:
        accent = theme_color(tokens.ACCENT_HOVER)
        text_primary = theme_color(tokens.TEXT_PRIMARY)
        text_sec = theme_color(tokens.TEXT_SECONDARY)
        accent_succ = theme_color(tokens.ACCENT_SUCCESS)

        if self.status_kind == "thinking":
            icon = "💭"
            iteration = self.meta.get("iteration")
            step_text = f" (step {iteration})" if iteration and iteration > 1 else ""
            if self.is_running:
                action = f"Thinking{step_text}..."
                badge = "working"
            else:
                elapsed = max(0.1, round(self._elapsed_s, 1))
                action = f"Thought for {elapsed}s"
                badge = "done"

        elif self.status_kind == "planning":
            icon = "🧠"
            action = "Planning implementation steps..." if self.is_running else "Plan formulated"
            badge = "active" if self.is_running else "done"

        elif self.status_kind == "repairing":
            icon = "🛠️"
            attempt = self.meta.get("attempt", 1)
            action = f"Self-correcting build/test errors (attempt {attempt})..." if self.is_running else "Error diagnosis complete"
            badge = "repairing" if self.is_running else "verified"

        elif self.status_kind == "running":
            # Pipeline / long-running work: show the live stage message sent by the runtime.
            stage = str(self.meta.get("stage") or "").strip()
            message = str(self.meta.get("message") or "").strip()
            failed = self.meta.get("ok") is False
            icon = "⚠️" if failed else "🏗️"
            label = message or (f"Running {stage}..." if stage else "Working...")
            if stage and message and stage.lower() not in message.lower():
                label = f"{stage}: {message}"
            action = label if self.is_running else (label if failed else f"{stage or 'Pipeline'} finished")
            badge = "failed" if failed else ("running" if self.is_running else "done")

        else:
            icon = "⚡"
            action = f"Agent: {self.status_kind.capitalize()}..." if self.is_running else self.status_kind.capitalize()
            badge = "active" if self.is_running else "done"

        self._icon_label.setText(icon)
        action_html = html.escape(action)
        color = accent if self.is_running else text_sec
        self._title_label.setText(
            f'<span style="color: {color}; font-weight: 600; font-size: 12px;">{action_html}</span>'
        )
        badge_color = text_sec if self.is_running else accent_succ
        self._badge_label.setText(
            f'<span style="color: {badge_color}; font-size: 10px; font-weight: 600;">{badge}</span>'
        )
        self._raw_text = f"{icon} {action}"

    @Slot()
    def _on_pulse(self) -> None:
        if not self.is_running:
            self._pulse_timer.stop()
            return
        self._pulse_tick += 1
        dots = "." * ((self._pulse_tick % 3) + 1)
        text_sec = theme_color(tokens.TEXT_SECONDARY)
        self._badge_label.setText(
            f'<span style="color: {text_sec}; font-size: 10px; font-weight: 600;">{dots}</span>'
        )

    def finalise(self) -> None:
        """Mark status activity completed."""
        self.is_running = False
        if self._pulse_timer.isActive():
            self._pulse_timer.stop()
        self._elapsed_s = max(0.1, round(time.time() - self._start_time, 1))
        self._refresh_display()

    def has_tokens(self) -> bool:
        return bool(self._raw_text)

    def deleteLater(self) -> None:
        try:
            if hasattr(self, "_pulse_timer") and self._pulse_timer and self._pulse_timer.isActive():
                self._pulse_timer.stop()
        except Exception:
            pass
        super().deleteLater()
