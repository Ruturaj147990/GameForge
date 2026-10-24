"""GameForge IDE — Chat Panel.

Provides a premium streaming chat interface connected directly to the
AgentService (in-process Qt signals, no HTTP, no WebSocket).
Features high-contrast markdown rendering, code block styling, one-click copy,
and intelligent scroll tracking.
"""

from __future__ import annotations

import json
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..services.agent_service import AgentService
from ..styles.dark_theme import theme_color, theme_stylesheet


# ── Message bubble widget ──────────────────────────────────────────────────────

class _MessageBubble(QFrame):
    """Single chat message bubble with role badge, timestamp, copy button, and auto-sizing markdown content."""

    # Colours per role: (bg, border_accent, role_label_color)
    _ROLE_THEMES = {
        "user":      ("#1a2236", "#6366f1", "#818cf8"),
        "assistant": ("#131b26", "#00d9a3", "#00d9a3"),
        "tool":      ("#1a1f2b", "#f59e0b", "#fbbf24"),
        "error":     ("#28161a", "#ef4444", "#f87171"),
        "system":    ("#111622", "#64748b", "#94a3b8"),
    }

    _DOCUMENT_CSS = """
        body {
            color: #f3f4f8;
            font-family: 'Segoe UI', -apple-system, sans-serif;
            font-size: 13px;
            line-height: 1.55;
            margin: 0;
            padding: 0;
        }
        p {
            margin: 4px 0;
        }
        h1, h2, h3, h4 {
            color: #ffffff;
            margin-top: 8px;
            margin-bottom: 4px;
            font-weight: 700;
        }
        h1 { font-size: 16px; }
        h2 { font-size: 15px; }
        h3 { font-size: 14px; }
        pre {
            background-color: #0b0e15;
            border: 1px solid #26304a;
            border-radius: 6px;
            padding: 8px 10px;
            margin: 6px 0;
            color: #e6edf3;
            font-family: 'Cascadia Code', 'Consolas', monospace;
            font-size: 12px;
            line-height: 1.4;
        }
        code {
            font-family: 'Cascadia Code', 'Consolas', monospace;
            color: #79c0ff;
            background-color: #161d2d;
            padding: 1px 4px;
            border-radius: 4px;
            font-size: 12px;
        }
        ul, ol {
            margin-left: 18px;
            margin-top: 4px;
            margin-bottom: 4px;
            padding-left: 0;
        }
        li {
            margin: 2px 0;
        }
        a {
            color: #6366f1;
            text-decoration: none;
        }
    """

    def __init__(self, role: str, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.role = role
        self._raw_text = text
        self.setObjectName("chat_message_bubble")

        bg, border_accent, role_color = self._ROLE_THEMES.get(
            role, ("#141a29", "#6366f1", "#f3f4f8")
        )
        bg, border_accent, role_color = (
            theme_color(bg), theme_color(border_accent), theme_color(role_color)
        )

        self.setStyleSheet(theme_stylesheet(f"""
            _MessageBubble#chat_message_bubble {{
                background-color: {bg};
                border-left: 3px solid {border_accent};
                border-top: 1px solid #1e263d;
                border-right: 1px solid #1e263d;
                border-bottom: 1px solid #1e263d;
                border-radius: 8px;
                margin: 4px 10px;
            }}
        """))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        # Header row
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        role_label = QLabel(role.upper())
        role_label.setStyleSheet(
            f"color: {role_color}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 0.8px; background: transparent; border: none;"
        )
        header.addWidget(role_label)
        header.addStretch()

        self._ts_label = QLabel("")
        self._ts_label.setStyleSheet(
            "color: #6b7280; font-size: 11px; background: transparent; border: none;"
        )
        header.addWidget(self._ts_label)

        # Copy button
        btn_copy = QPushButton("Copy")
        btn_copy.setObjectName("btn_copy_bubble")
        btn_copy.setToolTip("Copy message text to clipboard")
        btn_copy.setStyleSheet(theme_stylesheet("""
            QPushButton#btn_copy_bubble {
                background: #181f30;
                border: 1px solid #26304a;
                border-radius: 4px;
                padding: 2px 8px;
                color: #9ca3af;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton#btn_copy_bubble:hover {
                background: #222a42;
                border-color: #6366f1;
                color: #ffffff;
            }
        """))
        btn_copy.clicked.connect(self._copy_to_clipboard)
        header.addWidget(btn_copy)

        layout.addLayout(header)

        # Content widget: auto-sizing QTextBrowser with rich markdown support
        self._content = QTextBrowser()
        self._content.setReadOnly(True)
        self._content.setOpenExternalLinks(True)
        self._content.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._content.setStyleSheet("background: transparent; border: none; padding: 0;")
        self._content.document().setDefaultStyleSheet(theme_stylesheet(self._DOCUMENT_CSS))
        self._content.setProperty("gameforgeDocumentCss", self._DOCUMENT_CSS)

        if text:
            self._render_text(text)

        layout.addWidget(self._content)
        self._adjust_height()
        app = QApplication.instance()
        active_theme = app.property("gameforgeTheme") if app is not None else "dark"
        for widget in [self, *self.findChildren(QWidget)]:
            widget.setProperty("gameforgeTheme", active_theme or "dark")

    def _render_text(self, text: str) -> None:
        self._raw_text = text
        # If it contains markdown indicators, render markdown; else plain text
        if any(tok in text for tok in ("```", "#", "*", "_", "`", "[", "\n")):
            self._content.setMarkdown(text)
        else:
            self._content.setPlainText(text)
        self._adjust_height()

    def _adjust_height(self) -> None:
        doc = self._content.document()
        vp_width = self._content.viewport().width()
        if vp_width > 50:
            doc.setTextWidth(vp_width)
        else:
            parent_w = self.width() - 40
            if parent_w > 50:
                doc.setTextWidth(parent_w)
        # Add slight buffer for line spacing & margins
        h = int(doc.size().height()) + 16
        self._content.setFixedHeight(max(h, 36))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._adjust_height()

    def append_token(self, token: str) -> None:
        self._raw_text += token
        self._render_text(self._raw_text)

    def set_timestamp(self, ts: str) -> None:
        self._ts_label.setText(ts)

    def finalise(self) -> None:
        self.set_timestamp(time.strftime("%H:%M:%S"))
        self._adjust_height()

    def has_tokens(self) -> bool:
        return bool(self._raw_text.strip())

    @Slot()
    def _copy_to_clipboard(self) -> None:
        QApplication.clipboard().setText(self._raw_text)


# ── Status indicator widget ────────────────────────────────────────────────────

class _StatusBar(QWidget):
    """Thin status row showing agent state and model name."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 5, 12, 5)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(theme_stylesheet("color: #00d9a3; font-size: 11px;"))
        layout.addWidget(self._dot)

        self._label = QLabel("Ready")
        self._label.setStyleSheet(theme_stylesheet("color: #00d9a3; font-size: 12px; font-weight: 600;"))
        layout.addWidget(self._label)

        layout.addStretch()

        self._model_label = QLabel()
        self._model_label.setStyleSheet(theme_stylesheet(
            "color: #818cf8; font-size: 12px; font-weight: 700;"
        ))
        layout.addWidget(self._model_label)

    def set_ready(self) -> None:
        self._dot.setStyleSheet(theme_stylesheet("color: #00d9a3; font-size: 11px;"))
        self._label.setText("Ready")
        self._label.setStyleSheet(theme_stylesheet("color: #00d9a3; font-size: 12px; font-weight: 600;"))

    def set_busy(self, status: str = "THINKING") -> None:
        self._dot.setStyleSheet(theme_stylesheet("color: #f59e0b; font-size: 11px;"))
        self._label.setText(status)
        self._label.setStyleSheet(theme_stylesheet("color: #f59e0b; font-size: 12px; font-weight: 600;"))

    def set_error(self) -> None:
        self._dot.setStyleSheet(theme_stylesheet("color: #ef4444; font-size: 11px;"))
        self._label.setText("Error")
        self._label.setStyleSheet(theme_stylesheet("color: #ef4444; font-size: 12px; font-weight: 600;"))

    def set_model(self, model_name: str) -> None:
        self._model_label.setText(f"🤖 {model_name}")


# ── Chat panel ─────────────────────────────────────────────────────────────────

class ChatPanel(QWidget):
    """Main agentic chat panel.

    All communication with the model goes through AgentService (in-process
    QThread bridge) — no HTTP, no browser.
    """

    # Forwarded diff event for the main window to show the diff panel
    diff_pending = Signal(str, dict)

    def __init__(
        self,
        agent_service: AgentService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._agent = agent_service
        self._session_id: Optional[str] = None
        self._active_bubble: Optional[_MessageBubble] = None
        self._current_model = "gameforge-27b-sft:latest"
        self._last_prompt = ""
        self._ignore_active_task_events = False

        self._build_ui()
        self._connect_signals()
        self._init_session()

    # ── UI Construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toolbar row
        toolbar = QWidget()
        toolbar.setStyleSheet("background: #0c0e14; border-bottom: 1px solid #26304a;")
        toolbar.setFixedHeight(48)
        tbar_layout = QHBoxLayout(toolbar)
        tbar_layout.setContentsMargins(12, 6, 12, 6)
        tbar_layout.setSpacing(10)

        lbl = QLabel("🎮  GameForge Chat")
        lbl.setStyleSheet("color: #818cf8; font-weight: 800; font-size: 14px; letter-spacing: 0.5px;")
        tbar_layout.addWidget(lbl)
        tbar_layout.addStretch()

        model_lbl = QLabel("Model:")
        model_lbl.setStyleSheet("color: #9ca3af; font-size: 12px; font-weight: 600;")
        tbar_layout.addWidget(model_lbl)

        self._model_combo = QComboBox()
        self._model_combo.setObjectName("model_combo")
        self._model_combo.setMinimumWidth(230)
        self._model_combo.addItem("gameforge-27b-sft:latest")
        tbar_layout.addWidget(self._model_combo)

        btn_clear = QPushButton("Clear")
        btn_clear.setObjectName("btn_clear_chat")
        btn_clear.setMinimumWidth(70)
        btn_clear.clicked.connect(self._clear_chat)
        tbar_layout.addWidget(btn_clear)

        btn_new = QPushButton("New Session")
        btn_new.setObjectName("btn_new_session")
        btn_new.setMinimumWidth(110)
        btn_new.clicked.connect(self._new_session)
        tbar_layout.addWidget(btn_new)

        root.addWidget(toolbar)

        # Message scroll area
        self._scroll_area = QScrollArea()
        self._scroll_area.setObjectName("chat_scroll_area")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet("border: none; background: #0c0e14;")

        self._msg_container = QWidget()
        self._msg_container.setStyleSheet("background: #0c0e14;")
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(8, 12, 8, 12)
        self._msg_layout.setSpacing(8)
        self._msg_layout.addStretch()  # pushes messages to bottom initially

        self._scroll_area.setWidget(self._msg_container)
        root.addWidget(self._scroll_area, 1)

        # Status bar
        self._status_bar = _StatusBar()
        self._status_bar.setStyleSheet("background: #0c0e14; border-top: 1px solid #26304a;")
        self._status_bar.set_model(self._current_model)
        root.addWidget(self._status_bar)

        # Input row
        input_widget = QWidget()
        input_widget.setStyleSheet("background: #121622; border-top: 1px solid #26304a;")
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(12, 10, 12, 10)
        input_layout.setSpacing(10)

        self._input = QPlainTextEdit()
        self._input.setObjectName("chat_input")
        self._input.setPlaceholderText(
            "Describe what you want to build or fix… (Enter or Ctrl+Enter to send, Shift+Enter for newline)"
        )
        self._input.setFixedHeight(75)
        self._input.installEventFilter(self)
        input_layout.addWidget(self._input, 1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)
        self._btn_send = QPushButton("Send ▶")
        self._btn_send.setObjectName("btn_send")
        self._btn_send.setFixedWidth(96)
        self._btn_send.setFixedHeight(34)
        self._btn_send.clicked.connect(self._on_send)
        btn_col.addWidget(self._btn_send)

        self._btn_stop = QPushButton("Stop ■")
        self._btn_stop.setObjectName("btn_stop")
        self._btn_stop.setFixedWidth(96)
        self._btn_stop.setFixedHeight(34)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setEnabled(False)
        btn_col.addWidget(self._btn_stop)

        input_layout.addLayout(btn_col)
        root.addWidget(input_widget)

    def _connect_signals(self) -> None:
        self._agent.token_received.connect(self._on_token)
        self._agent.status_changed.connect(self._on_status)
        self._agent.tool_called.connect(self._on_tool_called)
        self._agent.tool_result.connect(self._on_tool_result)
        self._agent.diff_pending.connect(self._on_diff_pending)
        self._agent.error_occurred.connect(self._on_error)
        self._agent.task_done.connect(self._on_done)
        self._model_combo.currentTextChanged.connect(self._on_model_changed)

    def _init_session(self) -> None:
        """Create initial session asynchronously."""
        try:
            self._session_id = self._agent.create_session(
                name="Default Session",
                model_name="gameforge-27b-sft:latest",
                provider_type="ollama",
            )
            self._add_system_message(
                "🎮 **GameForge IDE is ready.**\n\n"
                "• **Model:** `gameforge-27b-sft:latest` (Ollama local inference)\n"
                "• **Capabilities:** C++, Blueprints, Python, shaders, diagnostics, staged builds\n"
                "• Ask a question or describe an Unreal Engine 5.7 task to begin."
            )
            self._status_bar.set_ready()
            QTimer.singleShot(500, self._load_models)
        except Exception as exc:
            self._add_error_message(f"Failed to initialise session: {exc}")

    def _load_models(self) -> None:
        try:
            models = self._agent.list_models()
            self._model_combo.blockSignals(True)
            self._model_combo.clear()
            for m in models:
                self._model_combo.addItem(m.get("id", m.get("name", "unknown")))
            idx = self._model_combo.findText("gameforge-27b-sft:latest")
            if idx >= 0:
                self._model_combo.setCurrentIndex(idx)
            self._model_combo.blockSignals(False)
        except Exception:
            pass

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot()
    def _on_send(self) -> None:
        # Preserve the exact composer payload; whitespace-only detection must
        # not mutate copied code, indentation, or deliberate boundary spaces.
        prompt = self._input.toPlainText()
        if not prompt.strip() or not self._session_id:
            return
        if self._agent.is_busy:
            self._status_bar.set_busy(
                "STOPPING PREVIOUS TASK" if self._agent.is_stopping else "TASK ALREADY RUNNING"
            )
            return

        self._last_prompt = prompt
        self._input.clear()
        self._add_bubble("user", prompt)

        # Start assistant bubble (will be filled by streaming tokens)
        self._active_bubble = self._add_bubble("assistant", "")

        self._btn_send.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._status_bar.set_busy("PLANNING")

        ok = self._agent.send(self._session_id, prompt)
        if not ok:
            self._input.setPlainText(self._last_prompt)
            self._btn_send.setEnabled(True)
            self._btn_stop.setEnabled(False)
            self._status_bar.set_ready()

    @Slot()
    def _on_stop(self) -> None:
        self._agent.stop()
        self._btn_stop.setEnabled(False)
        self._btn_send.setEnabled(False)
        self._status_bar.set_busy("STOPPING")
        if self._active_bubble:
            self._active_bubble.append_token("\n\n*[Stopped by user]*")
            self._active_bubble.finalise()
            self._active_bubble = None

    @Slot(str)
    def _on_token(self, token: str) -> None:
        if self._ignore_active_task_events or self._agent.is_stopping:
            return
        if self._active_bubble:
            was_at_bottom = self._is_scrolled_to_bottom()
            self._active_bubble.append_token(token)
            if was_at_bottom:
                self._scroll_to_bottom()

    @Slot(str, dict)
    def _on_status(self, status: str, _meta: dict) -> None:
        if self._ignore_active_task_events or self._agent.is_stopping:
            return
        omitted = int(_meta.get("omitted_history_messages", 0) or 0)
        if status == "PLANNING" and omitted:
            used = _meta.get("estimated_input_tokens", "?")
            budget = _meta.get("input_budget_tokens", "?")
            self._add_bubble(
                "tool",
                f"ℹ️ Context budget: omitted {omitted} older message(s) to fit "
                f"the estimated {used}/{budget} input-token budget. The current prompt is preserved in full.",
            )
        self._status_bar.set_busy(status)

    @Slot(str, dict)
    def _on_tool_called(self, tool_name: str, args: dict) -> None:
        if self._ignore_active_task_events or self._agent.is_stopping:
            return
        summary = f"🔧 **Tool Call:** `{tool_name}`"
        if args:
            summary += f"\n```json\n{json.dumps(args, indent=2)}\n```"
        self._add_bubble("tool", summary)

    @Slot(str, dict)
    def _on_tool_result(self, tool_name: str, result: dict) -> None:
        if self._ignore_active_task_events or self._agent.is_stopping:
            return
        status = result.get("status", "?")
        err = result.get("error", "")
        summary = f"✅ **Tool `{tool_name}` → `{status}`**"
        if err:
            summary += f"\n> ⚠️ Error: {err}"
        self._add_bubble("tool", summary)
        # Start new assistant bubble for continued response
        self._active_bubble = self._add_bubble("assistant", "")

    @Slot(str, dict)
    def _on_diff_pending(self, diff_id: str, meta: dict) -> None:
        if self._ignore_active_task_events or self._agent.is_stopping:
            return
        self.diff_pending.emit(diff_id, meta)
        self._add_bubble(
            "tool",
            f"📝 **Diff Ready for Review:** `{diff_id}`\n"
            f"• File: `{meta.get('file_path', 'unknown')}`\n"
            "• Open the **Diff Review** panel on the right to approve or reject.",
        )

    @Slot(str)
    def _on_error(self, error: str) -> None:
        if self._ignore_active_task_events or self._agent.is_stopping:
            self._ignore_active_task_events = False
            self._active_bubble = None
            self._btn_send.setEnabled(True)
            self._btn_stop.setEnabled(False)
            self._status_bar.set_ready()
            return
        if self._active_bubble:
            if not self._active_bubble.has_tokens():
                # Restore prompt if failed immediately
                if self._last_prompt and not self._input.toPlainText().strip():
                    self._input.setPlainText(self._last_prompt)
            self._active_bubble.finalise()
            self._active_bubble = None
        self._add_error_message(error)
        self._btn_send.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._status_bar.set_error()

    @Slot(str)
    def _on_done(self, _full_text: str) -> None:
        if self._ignore_active_task_events:
            self._ignore_active_task_events = False
            self._active_bubble = None
            self._btn_send.setEnabled(True)
            self._btn_stop.setEnabled(False)
            self._status_bar.set_ready()
            return
        if self._active_bubble:
            self._active_bubble.finalise()
            self._active_bubble = None
        self._btn_send.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._status_bar.set_ready()

    @Slot(str)
    def _on_model_changed(self, model_name: str) -> None:
        self._current_model = model_name
        self._status_bar.set_model(model_name)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _is_scrolled_to_bottom(self) -> bool:
        sb = self._scroll_area.verticalScrollBar()
        return sb.value() >= (sb.maximum() - 40)

    def _add_bubble(self, role: str, text: str) -> _MessageBubble:
        bubble = _MessageBubble(role, text)
        count = self._msg_layout.count()
        self._msg_layout.insertWidget(count - 1, bubble)
        self._scroll_to_bottom()
        return bubble

    def _add_system_message(self, text: str) -> None:
        self._add_bubble("system", text)

    def _add_error_message(self, text: str) -> None:
        self._add_bubble("error", f"⚠️ **Error:** {text}")

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(20, lambda: self._scroll_area.verticalScrollBar().setValue(
            self._scroll_area.verticalScrollBar().maximum()
        ))

    def _clear_chat(self) -> None:
        for i in reversed(range(self._msg_layout.count() - 1)):
            item = self._msg_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        self._add_system_message("Chat view cleared.")

    def _new_session(self) -> None:
        try:
            if self._agent.is_busy:
                self._ignore_active_task_events = True
                self._agent.stop()
                self._active_bubble = None
            self._session_id = self._agent.create_session(
                name="New Session",
                model_name=self._current_model,
                provider_type="ollama",
            )
            self._clear_chat()
            self._btn_send.setEnabled(not self._agent.is_busy)
            self._btn_stop.setEnabled(self._agent.is_busy)
            self._add_system_message(
                f"**New Session Initialised.**\n"
                f"Active model: `{self._current_model}`"
            )
        except Exception as exc:
            self._add_error_message(f"Failed to create session: {exc}")

    # ── Event filter (Enter / Ctrl+Enter to send, Shift+Enter for newline) ─────

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        if obj is self._input and event.type() == QEvent.KeyPress:
            ke: QKeyEvent = event
            if ke.key() in (Qt.Key_Return, Qt.Key_Enter):
                if ke.modifiers() & Qt.ShiftModifier:
                    # Allow standard newline insertion
                    return False
                # Enter or Ctrl+Enter sends
                self._on_send()
                return True
        return super().eventFilter(obj, event)
