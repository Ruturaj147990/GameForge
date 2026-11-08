"""GameForge IDE — Terminal Panel.

Embedded interactive terminal using QProcess + QPlainTextEdit.
Runs PowerShell by default, bounded to the workspace root.
Does NOT use subprocess.Popen; uses Qt's QProcess for proper event-loop integration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QProcess, Qt, Slot
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..styles import tokens
from ..styles.dark_theme import theme_color


class TerminalPanel(QWidget):
    """Embedded PowerShell terminal panel using QProcess."""

    def __init__(self, workspace_root: Path, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("terminalPanel")
        self.setAccessibleName("Embedded PowerShell Terminal")
        self._workspace = Path(workspace_root).resolve()
        self._process: QProcess | None = None
        self._build_ui()
        # Lazy start (Blueprint v2 §8.1): no shell process exists until the user runs a command.
        self._write_info(f"GameForge Terminal — {self._workspace}\nPowerShell starts with your first command.\n")

    # ── UI Construction ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("panel_header")
        header.setStyleSheet(f"background: {tokens.BG_PANEL}; border-bottom: 1px solid {tokens.BORDER};")
        header.setFixedHeight(36)
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(8, 4, 8, 4)
        title = QLabel("⬛  Terminal — PowerShell")
        title.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: {tokens.FONT_BODY_SM}px; font-weight: 600; letter-spacing: 0.6px;")
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()

        btn_clear = QPushButton("Clear")
        btn_clear.setObjectName("btn_term_clear")
        btn_clear.setAccessibleName("Clear terminal output")
        btn_clear.setToolTip("Clear all terminal output text")
        btn_clear.setMinimumWidth(58)
        btn_clear.setFixedHeight(26)
        btn_clear.setStyleSheet(
            f"QPushButton {{"
            f"  background: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 2px {tokens.SPACE_SM}px; font-size: {tokens.FONT_BODY_SM}px;"
            f"}}"
            f"QPushButton:hover {{ background: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}"
        )
        hdr_layout.addWidget(btn_clear)

        btn_restart = QPushButton("↺")
        btn_restart.setObjectName("btn_term_restart")
        btn_restart.setAccessibleName("Restart PowerShell process")
        btn_restart.setToolTip("Restart shell process")
        btn_restart.setFixedSize(30, 26)
        btn_restart.setStyleSheet(
            f"QPushButton {{"
            f"  background: {tokens.BG_SURFACE}; color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER}; border-radius: {tokens.RADIUS}px;"
            f"  padding: 0px; font-size: 14px;"
            f"}}"
            f"QPushButton:hover {{ background: {tokens.BG_HOVER}; color: {tokens.TEXT_PRIMARY}; }}"
        )
        btn_restart.clicked.connect(self._restart_shell)
        hdr_layout.addWidget(btn_restart)
        layout.addWidget(header)

        # Output area
        self._output = QPlainTextEdit()
        self._output.setObjectName("terminal_output")
        self._output.setAccessibleName("PowerShell terminal output")
        self._output.setReadOnly(True)
        font = QFont("Cascadia Code")
        if not font.exactMatch():
            font.setFamily("Consolas")
        font.setPointSize(11)
        self._output.setFont(font)
        self._output.setStyleSheet(
            f"background: {tokens.BG_ROOT}; color: {tokens.TEXT_PRIMARY}; border: none;"
            f" selection-background-color: {tokens.ACCENT_PRIMARY}; selection-color: {tokens.TEXT_PRIMARY};"
        )
        layout.addWidget(self._output, 1)

        # Input row
        input_row = QWidget()
        input_row.setObjectName("panel_action_bar")
        input_row.setStyleSheet(f"background: {tokens.BG_PANEL}; border-top: 1px solid {tokens.BORDER};")
        input_row.setFixedHeight(36)
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(8, 4, 8, 4)
        input_layout.setSpacing(6)

        prompt_lbl = QLabel("PS❯")
        prompt_lbl.setStyleSheet(f"color: {tokens.ACCENT_HOVER}; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: {tokens.FONT_BODY_SM}px; font-weight: bold;")
        input_layout.addWidget(prompt_lbl)

        self._cmd_input = QLineEdit()
        self._cmd_input.setObjectName("terminal_input")
        self._cmd_input.setAccessibleName("Terminal command input")
        self._cmd_input.setPlaceholderText("Enter PowerShell command…")
        self._cmd_input.setStyleSheet(
            f"background: transparent; border: none; color: {tokens.TEXT_PRIMARY};"
            f" font-family: 'Cascadia Code', 'Consolas', monospace; font-size: {tokens.FONT_BODY}px;"
        )
        self._cmd_input.returnPressed.connect(self._on_send_command)
        input_layout.addWidget(self._cmd_input, 1)

        btn_run = QPushButton("▶")
        btn_run.setObjectName("btn_term_run")
        btn_run.setAccessibleName("Execute command")
        btn_run.setToolTip("Run command (Enter)")
        btn_run.setFixedSize(28, 28)
        btn_run.setStyleSheet(
            f"QPushButton {{"
            f"  background: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY};"
            f"  border: none; border-radius: {tokens.RADIUS}px; padding: 0px; font-size: 14px;"
            f"}}"
            f"QPushButton:hover {{ background: {tokens.ACCENT_HOVER}; }}"
        )
        btn_run.clicked.connect(self._on_send_command)
        input_layout.addWidget(btn_run)
        layout.addWidget(input_row)

        btn_clear.clicked.connect(self._output.clear)

    # ── Shell lifecycle ──────────────────────────────────────────────────────

    def _start_shell(self) -> None:
        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(self._workspace))
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.stateChanged.connect(self._on_state_changed)
        # PowerShell with non-interactive output (still interactive via stdin)
        self._process.start("powershell.exe", ["-NoLogo", "-NonInteractive"])
        self._process.waitForStarted(5000)

    def _restart_shell(self) -> None:
        self.shutdown()
        self._output.appendPlainText("\n--- Shell stopped; it restarts with your next command ---\n")

    def set_workspace(self, new_workspace: Path) -> None:
        """Switch active terminal directory to new workspace with clean exit."""
        self._workspace = Path(new_workspace).resolve()
        self.shutdown()
        self._write_info(f"\n--- Switched to workspace: {self._workspace} ---\nPowerShell starts with your next command.\n")

    def shutdown(self) -> None:
        """Cleanly terminate shell process on shutdown or workspace change."""
        if self._process is not None:
            try:
                if self._process.state() != QProcess.NotRunning:
                    self._process.kill()
                    self._process.waitForFinished(1000)
            except Exception:
                pass
            self._process = None

    # ── Output handlers ──────────────────────────────────────────────────────

    @Slot()
    def _on_stdout(self) -> None:
        if not self._process:
            return
        data = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._write_out(data)

    @Slot()
    def _on_stderr(self) -> None:
        if not self._process:
            return
        data = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
        self._write_err(data)

    @Slot()
    def _on_state_changed(self, state) -> None:
        if state == QProcess.NotRunning:
            self._write_err("\n[Shell process terminated]\n")

    # ── Command dispatch ─────────────────────────────────────────────────────

    @Slot()
    def run_command(self, cmd: Optional[str] = None) -> None:
        """Adapter for MainWindow and automation to run commands directly."""
        if cmd is not None:
            self._cmd_input.setText(cmd)
        self._on_send_command()

    def _on_send_command(self) -> None:
        cmd = self._cmd_input.text()
        if not cmd.strip():
            return
        self._cmd_input.clear()
        self._write_prompt(cmd)
        if self._process is None or self._process.state() == QProcess.NotRunning:
            self._start_shell()
        if self._process and self._process.state() == QProcess.Running:
            self._process.write((cmd + "\n").encode("utf-8"))
        else:
            self._write_err("Shell is not running. Restart with ↺.\n")

    # ── Styled writing helpers ───────────────────────────────────────────────

    def _write_out(self, text: str) -> None:
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(theme_color("#c8d0e8")))
        cursor.insertText(text, fmt)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

    def _write_err(self, text: str) -> None:
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(theme_color("#ff6b6b")))
        cursor.insertText(text, fmt)
        self._output.setTextCursor(cursor)

    def _write_info(self, text: str) -> None:
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(theme_color("#8891aa")))
        cursor.insertText(text, fmt)
        self._output.setTextCursor(cursor)

    def _write_prompt(self, cmd: str) -> None:
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(theme_color("#6c63ff")))
        cursor.insertText(f"PS❯ {cmd}\n", fmt)
        self._output.setTextCursor(cursor)

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)

    def deleteLater(self) -> None:
        self.shutdown()
        super().deleteLater()
