"""GameForge IDE — Chat Panel.

Provides a premium streaming chat interface connected directly to the
AgentService (in-process Qt signals, no HTTP, no WebSocket).
Features high-contrast markdown rendering, code block styling, one-click copy,
and intelligent scroll tracking.
"""

from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path
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

from ...core.settings import get_settings
from ...backend.unreal_context import UnrealEditorContext, load_unreal_context
from ..services.action_runner import ActionRunner
from ..services.agent_service import AgentService
from .approval_card import ApprovalCard
from .diff_card import DiffApprovalCard, FileChangedNotification
from .plan_card import PlanCard
from .activity_card import (
    StatusActivityItem,
    ToolActivityItem,
    format_target_path,
    format_tool_activity,
)
from ...backend.models.modes import AutonomyProfile, TaskMode
from ..styles import tokens
from ..styles.dark_theme import theme_color, theme_stylesheet


# ── Message bubble widget ──────────────────────────────────────────────────────

class _MessageBubble(QFrame):
    """Single chat message bubble with role badge, timestamp, copy button, and auto-sizing markdown content."""

    # Colours per role: (bg, border_accent, role_label_color)
    _ROLE_THEMES = {
        "user":      (tokens.BG_ACTIVE, tokens.ACCENT_PRIMARY, tokens.ACCENT_HOVER),
        "assistant": (tokens.BG_PANEL, tokens.ACCENT_SUCCESS, tokens.ACCENT_SUCCESS),
        "tool":      (tokens.BG_SURFACE, tokens.ACCENT_WARNING, tokens.ACCENT_WARNING),
        "error":     (tokens.BG_SURFACE, tokens.ACCENT_ERROR, tokens.ACCENT_ERROR),
        "system":    (tokens.BG_ROOT, tokens.BORDER, tokens.TEXT_SECONDARY),
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
            color: #f3f4f8;
            margin-top: 8px;
            margin-bottom: 4px;
            font-weight: 700;
        }
        h1 { font-size: 16px; }
        h2 { font-size: 15px; }
        h3 { font-size: 14px; }
        pre {
            background-color: #0c0e14;
            border: 1px solid #231c34;
            border-radius: 6px;
            padding: 8px 10px;
            margin: 6px 0;
            color: #f3f4f8;
            font-family: 'Cascadia Code', 'Consolas', monospace;
            font-size: 12px;
            line-height: 1.4;
        }
        code {
            font-family: 'Cascadia Code', 'Consolas', monospace;
            color: #8b5cf6;
            background-color: #120f1d;
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
        blockquote {
            border-left: 3px solid #7c3aed;
            margin: 6px 0 6px 6px;
            padding-left: 8px;
            color: #9d95b0;
            font-style: italic;
        }
        hr {
            border: 0;
            border-top: 1px solid #231c34;
            margin: 8px 0;
        }
        a {
            color: #7c3aed;
            text-decoration: none;
        }
    """

    def __init__(self, role: str, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.role = role
        self._raw_text = text
        self.setObjectName("chat_message_bubble")
        self.setAccessibleName(f"{role.capitalize()} chat message")

        bg, border_accent, role_color = self._ROLE_THEMES.get(
            role, (tokens.BG_PANEL, tokens.ACCENT_PRIMARY, tokens.TEXT_PRIMARY)
        )
        bg, border_accent, role_color = (
            theme_color(bg), theme_color(border_accent), theme_color(role_color)
        )

        radius_lg = getattr(tokens, "RADIUS_LG", 8)
        self.setStyleSheet(theme_stylesheet(f"""
            _MessageBubble#chat_message_bubble {{
                background-color: {bg};
                border-left: 3px solid {border_accent};
                border-top: 1px solid {tokens.BORDER};
                border-right: 1px solid {tokens.BORDER};
                border-bottom: 1px solid {tokens.BORDER};
                border-radius: {radius_lg}px;
                margin: 6px 12px;
            }}
            _MessageBubble#chat_message_bubble:hover {{
                border-top: 1px solid {tokens.BORDER_FOCUS};
                border-right: 1px solid {tokens.BORDER_FOCUS};
                border-bottom: 1px solid {tokens.BORDER_FOCUS};
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
        btn_copy.setAccessibleName("Copy message content")
        btn_copy.setToolTip("Copy message text to clipboard")
        btn_copy.setStyleSheet(theme_stylesheet(f"""
            QPushButton#btn_copy_bubble {{
                background: {tokens.BG_SURFACE};
                border: 1px solid {tokens.BORDER};
                border-radius: 4px;
                padding: 2px 8px;
                color: {tokens.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton#btn_copy_bubble:hover {{
                background: {tokens.BG_HOVER};
                border-color: {tokens.ACCENT_PRIMARY};
                color: {tokens.TEXT_PRIMARY};
            }}
        """))
        btn_copy.clicked.connect(self._copy_to_clipboard)
        self._btn_copy = btn_copy
        header.addWidget(btn_copy)

        self.set_timestamp(time.strftime("%H:%M:%S"))
        layout.addLayout(header)

        # Content widget: auto-sizing QTextBrowser with rich markdown support
        self._content = QTextBrowser()
        self._content.setReadOnly(True)
        self._content.setOpenExternalLinks(True)
        self._content.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
        )
        self._content.setContextMenuPolicy(Qt.DefaultContextMenu)
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

    @staticmethod
    def _markdown_to_html(text: str) -> str:
        blocks = []
        def sub_block(m):
            code = m.group(2)
            escaped = html.escape(code.rstrip())
            idx = len(blocks)
            blocks.append(f"<pre><code>{escaped}</code></pre>")
            return f"___GF_CODE_BLOCK_{idx}___"

        pattern = r"```([a-zA-Z0-9_\-\+]*)[^\S\r\n]*\n(.*?)```"
        text_with_blocks = re.sub(pattern, sub_block, text, flags=re.DOTALL)

        # Handle unclosed/trailing code block during active streaming
        unclosed_match = re.search(r"```([a-zA-Z0-9_\-\+]*)(?:[^\S\r\n]*\n(.*))?$", text_with_blocks, flags=re.DOTALL)
        if unclosed_match:
            code_content = unclosed_match.group(2) or ""
            escaped = html.escape(code_content)
            idx = len(blocks)
            blocks.append(f"<pre><code>{escaped}</code></pre>")
            text_with_blocks = text_with_blocks[:unclosed_match.start()] + f"___GF_CODE_BLOCK_{idx}___"

        def _format_inline(raw: str) -> str:
            res = html.escape(raw)
            # inline code
            res = re.sub(r"`([^`]+)`", r"<code>\1</code>", res)
            # bold
            res = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", res)
            res = re.sub(r"__([^_]+)__", r"<b>\1</b>", res)
            # links
            res = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', res)
            return res

        lines = text_with_blocks.split("\n")
        out = []
        in_ul = False
        in_ol = False

        def _flush_lists():
            nonlocal in_ul, in_ol
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if in_ol:
                out.append("</ol>")
                in_ol = False

        for line in lines:
            if "___GF_CODE_BLOCK_" in line:
                _flush_lists()
                out.append(line)
                continue

            s = line.strip()
            if not s:
                _flush_lists()
                out.append("<p></p>")
                continue

            if s in ("---", "***", "___"):
                _flush_lists()
                out.append("<hr>")
                continue

            if s.startswith("> "):
                _flush_lists()
                out.append(f"<blockquote>{_format_inline(s[2:])}</blockquote>")
                continue

            if s.startswith(("- ", "* ")):
                if in_ol:
                    out.append("</ol>")
                    in_ol = False
                if not in_ul:
                    out.append("<ul>")
                    in_ul = True
                out.append(f"<li>{_format_inline(s[2:])}</li>")
                continue

            ol_match = re.match(r"^(\d+)\.\s+(.*)$", s)
            if ol_match:
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                if not in_ol:
                    out.append("<ol>")
                    in_ol = True
                out.append(f"<li>{_format_inline(ol_match.group(2))}</li>")
                continue

            _flush_lists()

            if s.startswith("#### "):
                out.append(f"<h5>{html.escape(s[5:])}</h5>")
            elif s.startswith("### "):
                out.append(f"<h4>{html.escape(s[4:])}</h4>")
            elif s.startswith("## "):
                out.append(f"<h3>{html.escape(s[3:])}</h3>")
            elif s.startswith("# "):
                out.append(f"<h2>{html.escape(s[2:])}</h2>")
            else:
                out.append(f"<p>{_format_inline(line)}</p>")

        _flush_lists()

        html_out = "\n".join(out)
        for idx, b in enumerate(blocks):
            html_out = html_out.replace(f"___GF_CODE_BLOCK_{idx}___", b)
        return html_out

    def _render_text(self, text: str) -> None:
        self._raw_text = text
        # If it contains markdown indicators, render rich high-contrast HTML; else plain text
        if any(tok in text for tok in ("```", "#", "*", "_", "`", "[", "\n")):
            self._content.setHtml(self._markdown_to_html(text))
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
        if hasattr(self, "_btn_copy"):
            self._btn_copy.setText("Copied! ✓")
            def _reset_btn():
                try:
                    if hasattr(self, "_btn_copy") and self._btn_copy:
                        self._btn_copy.setText("Copy")
                except (RuntimeError, Exception):
                    pass
            QTimer.singleShot(1500, _reset_btn)


# ── Status indicator widget ────────────────────────────────────────────────────

class _StatusBar(QWidget):
    """Thin status row showing agent state, animated indeterminate activity, and model name."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 5, 12, 5)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(theme_stylesheet(f"color: {tokens.ACCENT_SUCCESS}; font-size: 11px;"))
        layout.addWidget(self._dot)

        self._label = QLabel("Ready")
        self._label.setStyleSheet(theme_stylesheet(f"color: {tokens.ACCENT_SUCCESS}; font-size: 12px; font-weight: 600;"))
        layout.addWidget(self._label)

        # Pulse timer for busy states
        self._pulse_frames = ["◐", "◓", "◑", "◒"]
        self._pulse_idx = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(250)
        self._pulse_timer.timeout.connect(self._on_pulse)

        # Unreal connection badge
        self._ue_label = QLabel("Unreal: Disconnected")
        self._ue_label.setStyleSheet(theme_stylesheet(f"color: {tokens.TEXT_SECONDARY}; font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: 6px; background: {tokens.BG_SURFACE};"))
        self._ue_label.setVisible(False)
        layout.addWidget(self._ue_label)

        layout.addStretch()

        self._model_label = QLabel()
        self._model_label.setStyleSheet(theme_stylesheet(
            f"color: {tokens.ACCENT_HOVER}; font-size: 12px; font-weight: 700;"
        ))
        self._model_label.setVisible(False)
        layout.addWidget(self._model_label)

    def _on_pulse(self) -> None:
        self._pulse_idx = (self._pulse_idx + 1) % len(self._pulse_frames)
        self._dot.setText(self._pulse_frames[self._pulse_idx])

    def set_ready(self) -> None:
        self._pulse_timer.stop()
        self._dot.setText("●")
        self._dot.setStyleSheet(theme_stylesheet(f"color: {tokens.ACCENT_SUCCESS}; font-size: 11px;"))
        self._label.setText("Ready")
        self._label.setStyleSheet(theme_stylesheet(f"color: {tokens.ACCENT_SUCCESS}; font-size: 12px; font-weight: 600;"))

    def set_busy(self, status: str = "THINKING") -> None:
        self._label.setText(status)
        self._label.setStyleSheet(theme_stylesheet(f"color: {tokens.ACCENT_WARNING}; font-size: 12px; font-weight: 600;"))
        self._dot.setStyleSheet(theme_stylesheet(f"color: {tokens.ACCENT_WARNING}; font-size: 11px;"))
        if not self._pulse_timer.isActive():
            self._pulse_timer.start()

    def set_error(self) -> None:
        self._pulse_timer.stop()
        self._dot.setText("●")
        self._dot.setStyleSheet(theme_stylesheet(f"color: {tokens.ACCENT_ERROR}; font-size: 11px;"))
        self._label.setText("Error")
        self._label.setStyleSheet(theme_stylesheet(f"color: {tokens.ACCENT_ERROR}; font-size: 12px; font-weight: 600;"))

    def set_model(self, model_name: str) -> None:
        self._model_label.setText(f"🤖 {model_name}")

    def set_unreal_status(self, connected: bool, project_name: str = "", active_asset: str = "") -> None:
        # Called by a 2.5 s poll; setStyleSheet re-polishes the widget, so only touch it when something changed.
        key = (connected, project_name, active_asset)
        if getattr(self, "_ue_status_key", None) == key:
            return
        self._ue_status_key = key
        if connected:
            txt = f"UE Linked: {project_name}" if project_name else "UE Linked"
            if active_asset:
                txt += f" ({active_asset})"
            self._ue_label.setText(txt)
            self._ue_label.setStyleSheet(theme_stylesheet("color: #00d9a3; font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: 3px; background: #0e2922; border: 1px solid #00d9a3;"))
        else:
            self._ue_label.setText("Unreal: Disconnected")
            self._ue_label.setStyleSheet(theme_stylesheet("color: #9d95b0; font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: 6px; background: #120f1d;"))



# ── Start Screen Widget ────────────────────────────────────────────────────────

class _StartScreen(QWidget):
    """Empty-session start screen with assistant guidance and prompt suggestions."""

    make_game_clicked = Signal(str)
    ask_question_clicked = Signal()
    open_project_clicked = Signal()
    play_game_clicked = Signal(str)

    def __init__(self, workspace_root: Optional[Path], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("start_screen")
        self._raw_text = ""
        self._workspace = Path(workspace_root) if workspace_root else None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 24, 20, 24)
        root_layout.setSpacing(16)
        root_layout.setAlignment(Qt.AlignCenter)

        # Hero header
        hero_box = QVBoxLayout()
        hero_box.setSpacing(6)
        hero_box.setAlignment(Qt.AlignCenter)
        lbl_title = QLabel("🎮 GameForge Assistant")
        lbl_title.setObjectName("start_hero_title")
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {tokens.TEXT_PRIMARY};")
        hero_box.addWidget(lbl_title)

        lbl_sub = QLabel("Autonomous software engineering and game development for Unreal Engine 5.\nSubmit natural-language requests below to create, modify, inspect, or build.")
        lbl_sub.setObjectName("start_hero_subtitle")
        lbl_sub.setAlignment(Qt.AlignCenter)
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet(f"font-size: 12px; color: {tokens.TEXT_SECONDARY}; line-height: 1.4;")
        hero_box.addWidget(lbl_sub)
        root_layout.addLayout(hero_box)

        # Quick Guidance & Prompt Suggestions Card
        hints_box = QFrame()
        hints_box.setObjectName("start_hints_card")
        hints_box.setStyleSheet(f"""
            QFrame#start_hints_card {{
                background-color: {tokens.BG_PANEL};
                border: 1px solid {tokens.BORDER};
                border-radius: {tokens.RADIUS}px;
                padding: 12px;
            }}
        """)
        hints_layout = QVBoxLayout(hints_box)
        hints_layout.setSpacing(8)

        lbl_hints_hdr = QLabel("Quick prompt suggestions:")
        lbl_hints_hdr.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: 11px; font-weight: 600; text-transform: uppercase;")
        hints_layout.addWidget(lbl_hints_hdr)

        examples = [
            ("✨ Create Game", "Create a top-down roguelike with dash mechanics"),
            ("🔧 Source Edit", "Add stamina consumption to dash in PlayerController.cpp"),
            ("🚀 Engine Build", "/build project and execute automation scenarios"),
        ]
        for icon_tag, prompt_text in examples:
            btn_ex = QPushButton(f"{icon_tag}  •  \"{prompt_text}\"")
            btn_ex.setCursor(Qt.PointingHandCursor)
            btn_ex.setStyleSheet(f"""
                QPushButton {{
                    background: {tokens.BG_SURFACE};
                    color: {tokens.TEXT_PRIMARY};
                    border: 1px solid {tokens.BORDER};
                    border-radius: 4px;
                    padding: 8px 12px;
                    font-size: 12px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background: {tokens.BG_HOVER};
                    border-color: {tokens.ACCENT_PRIMARY};
                }}
            """)
            btn_ex.clicked.connect(lambda _, txt=prompt_text: self.make_game_clicked.emit(txt))
            hints_layout.addWidget(btn_ex)

        root_layout.addWidget(hints_box)

    def _find_recent_games(self) -> list[tuple[str, Path, Optional[Path]]]:
        if not self._workspace or not Path(self._workspace).exists():
            return []
        ws = Path(self._workspace)
        results = []
        try:
            for d in (ws / "Games", ws):
                if not d.is_dir():
                    continue
                for item in d.iterdir():
                    if item.is_dir() and item.name not in (".gameforge", "Saved", "Source", "Intermediate", "Binaries", "scratch"):
                        report = item / "Saved" / "GameForge" / "pipeline_report.json"
                        shot = item / "Saved" / "GameForge" / "packaged_gameplay.png"
                        if report.is_file():
                            results.append((item.name, item, shot if shot.is_file() else None))
                        elif (item / f"{item.name}.uproject").is_file():
                            results.append((item.name, item, None))
        except Exception:
            pass
        return results


# ── Chat panel ─────────────────────────────────────────────────────────────────

class ChatPanel(QWidget):
    openDesignRequested = Signal(str)
    """Main agentic chat panel.

    All communication with the model goes through AgentService (in-process
    QThread bridge) — no HTTP, no browser.
    """

    # Streaming and lifecycle signals
    diff_pending = Signal(str, dict)
    plan_received = Signal(dict)
    file_changed = Signal(str, dict)
    task_mode_changed = Signal(str)
    autonomy_changed = Signal(str)
    action_finished = Signal(str, dict)
    slash_command_executed = Signal(str, str)
    model_changed = Signal(str)
    models_loaded = Signal(list)
    unreal_status_changed = Signal(bool, str, str)
    open_project_requested = Signal()

    def __init__(
        self,
        agent_service: Optional[AgentService] = None,
        workspace_root: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        if agent_service is None:
            agent_service = AgentService(Path(workspace_root or "."))
            self._owns_agent = True
        else:
            self._owns_agent = False
        self._agent = agent_service
        self._workspace = workspace_root or getattr(agent_service, "workspace_root", None)
        self._session_id: Optional[str] = None
        self._active_bubble: Optional[_MessageBubble] = None
        self._active_tool_item: Optional[ToolActivityItem] = None
        self._active_status_item: Optional[StatusActivityItem] = None
        self._start_screen: Optional[_StartScreen] = None
        self._current_model = get_settings().model_for("chat")
        self._last_prompt = ""
        self._ignore_active_task_events = False
        self._last_unreal_sync = ""
        self._tokens_streamed_in_turn = False
        self._token_buffer = ""
        self._cards: dict = {}
        self._plan_cards: dict = {}
        self._runner = ActionRunner(Path(self._workspace or "."), parent=self)
        self._runner.progress.connect(self._on_action_progress)
        self._runner.finished.connect(self._on_action_finished)

        self._build_ui()
        self._connect_signals()
        self._init_session()
        QTimer.singleShot(0, self._restore_pending_approvals)
        self._setup_unreal_sync()

    def set_workspace(self, agent_service: AgentService, new_workspace: Path) -> None:
        """Switch chat panel to a new workspace and start a fresh session."""
        self._agent = agent_service
        self._workspace = Path(new_workspace).resolve()
        self._runner.shutdown()
        self._runner = ActionRunner(self._workspace, parent=self)
        self._runner.progress.connect(self._on_action_progress)
        self._runner.finished.connect(self._on_action_finished)
        self._cards = {}
        self._new_session()
        QTimer.singleShot(0, self._restore_pending_approvals)
        self._check_unreal_context_sync()

    def deleteLater(self) -> None:
        """Cleanly terminate background runner, timers, and any internally-owned AgentService."""
        try:
            if hasattr(self, "_ue_sync_timer") and self._ue_sync_timer.isActive():
                self._ue_sync_timer.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "_status_bar") and hasattr(self._status_bar, "_pulse_timer") and self._status_bar._pulse_timer.isActive():
                self._status_bar._pulse_timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, "_owns_agent", False) and hasattr(self, "_agent") and self._agent:
                self._agent.shutdown()
        except Exception:
            pass
        try:
            if hasattr(self, "_active_tool_item") and self._active_tool_item:
                self._active_tool_item.deleteLater()
                self._active_tool_item = None
        except Exception:
            pass
        try:
            if hasattr(self, "_active_status_item") and self._active_status_item:
                self._active_status_item.deleteLater()
                self._active_status_item = None
        except Exception:
            pass
        try:
            if hasattr(self, "_runner") and self._runner:
                self._runner.shutdown()
        except Exception:
            pass
        super().deleteLater()

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

        # Two Independent Controls: Task Approach Mode and Autonomy Profile
        self.lbl_task_mode = QLabel("Approach:", toolbar)
        self.lbl_task_mode.setObjectName("lbl_task_mode")
        self.lbl_task_mode.setStyleSheet("color: #9ca3af; font-size: 11px; font-weight: 600;")
        tbar_layout.addWidget(self.lbl_task_mode)

        self.task_mode_combo = QComboBox(toolbar)
        self.task_mode_combo.setObjectName("task_mode_combo")
        self.taskModeCombo = self.task_mode_combo
        self.task_mode_combo.setAccessibleName("Task Approach Mode Selector")
        self.task_mode_combo.setToolTip("Task Approach: Planning (deliberative with interactive plan) vs Fast (immediate autonomous execution)")
        self.task_mode_combo.addItems(["Planning", "Fast"])
        cfg_settings = get_settings()
        default_mode = "Planning" if getattr(cfg_settings, "default_task_mode", "planning").lower() == "planning" else "Fast"
        self.task_mode_combo.setCurrentText(default_mode)
        self.task_mode_combo.setStyleSheet(f"""
            QComboBox#task_mode_combo {{
                background-color: {tokens.BG_SURFACE};
                color: {tokens.TEXT_PRIMARY};
                border: 1px solid {tokens.BORDER};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 12px;
                font-weight: 600;
            }}
            QComboBox#task_mode_combo:hover {{
                border-color: {tokens.BORDER_FOCUS};
            }}
        """)
        self.task_mode_combo.currentTextChanged.connect(self._on_task_mode_changed)
        tbar_layout.addWidget(self.task_mode_combo)

        self.lbl_autonomy = QLabel("Autonomy:", toolbar)
        self.lbl_autonomy.setObjectName("lbl_autonomy_profile")
        self.lbl_autonomy.setStyleSheet("color: #9ca3af; font-size: 11px; font-weight: 600;")
        tbar_layout.addWidget(self.lbl_autonomy)

        self.autonomy_combo = QComboBox(toolbar)
        self.autonomy_combo.setObjectName("autonomy_combo")
        self.autonomy_profile_combo = self.autonomy_combo
        self.autonomyCombo = self.autonomy_combo
        self.autonomy_combo.setAccessibleName("Autonomy Profile Selector")
        self.autonomy_combo.setToolTip("Autonomy Profile: Manual (explicit approval for edits/commands), Auto-Edit (auto file edits), Agentic (fully autonomous safe ops)")
        self.autonomy_combo.addItems(["Manual", "Auto-Edit", "Agentic"])
        default_autonomy_raw = getattr(cfg_settings, "default_autonomy_profile", "agentic").lower()
        default_autonomy = "Manual" if default_autonomy_raw == "manual" else ("Auto-Edit" if "auto" in default_autonomy_raw else "Agentic")
        self.autonomy_combo.setCurrentText(default_autonomy)
        self.autonomy_combo.setStyleSheet(f"""
            QComboBox#autonomy_combo {{
                background-color: {tokens.BG_SURFACE};
                color: {tokens.TEXT_PRIMARY};
                border: 1px solid {tokens.BORDER};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 12px;
                font-weight: 600;
            }}
            QComboBox#autonomy_combo:hover {{
                border-color: {tokens.BORDER_FOCUS};
            }}
        """)
        self.autonomy_combo.currentTextChanged.connect(self._on_autonomy_changed)
        tbar_layout.addWidget(self.autonomy_combo)

        model_lbl = QLabel("Model:")
        model_lbl.setStyleSheet("color: #9ca3af; font-size: 12px; font-weight: 600;")
        tbar_layout.addWidget(model_lbl)

        self._model_combo = QComboBox()
        self._model_combo.setObjectName("model_combo")
        self._model_combo.setMinimumWidth(230)
        self._model_combo.addItem(get_settings().model_for("chat"))
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

        # UX plan step 1: the main toolbar already has Model / Clear Chat / New Session (calling the same handlers),
        # so the duplicates here are hidden. The combo stays as the panel's internal model state.
        for w in (model_lbl, self._model_combo, btn_clear, btn_new):
            w.setVisible(False)

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

        # Context chips row (Antigravity & Claude Code inspired shortcuts)
        self._chips_widget = QWidget()
        self._chips_widget.setObjectName("chat_chips_bar")
        self._chips_widget.setStyleSheet("background: #0f131c; border-top: 1px solid #1e263d; padding: 2px 8px;")
        chips_layout = QHBoxLayout(self._chips_widget)
        chips_layout.setContentsMargins(8, 4, 8, 4)
        chips_layout.setSpacing(6)

        chips_lbl = QLabel("Context:")
        chips_lbl.setStyleSheet("color: #9d95b0; font-size: 11px; font-weight: 600;")
        chips_layout.addWidget(chips_lbl)

        self._btn_chip_ue = QPushButton("🎮 @ue")
        self._btn_chip_ue.setToolTip("Insert Unreal Engine context tag")
        self._btn_chip_actor = QPushButton("🎭 @actor")
        self._btn_chip_actor.setToolTip("Insert Selected Actor context tag")
        self._btn_chip_asset = QPushButton("📦 @asset")
        self._btn_chip_asset.setToolTip("Insert Active Asset context tag")
        self._btn_cmd_build = QPushButton("⚙ /build")
        self._btn_cmd_build.setToolTip("Trigger Unreal staged build")
        self._btn_cmd_clear = QPushButton("🗑 /clear")
        self._btn_cmd_clear.setToolTip("Clear chat transcript")

        for chip_btn in (self._btn_chip_ue, self._btn_chip_actor, self._btn_chip_asset, self._btn_cmd_build, self._btn_cmd_clear):
            chip_btn.setFixedHeight(22)
            chip_btn.setStyleSheet(theme_stylesheet("""
                QPushButton {
                    background: #182030;
                    border: 1px solid #28354f;
                    border-radius: 3px;
                    color: #94a3b8;
                    font-size: 11px;
                    padding: 1px 6px;
                }
                QPushButton:hover {
                    background: #232e46;
                    border-color: #6366f1;
                    color: #e2e8f0;
                }
            """))
            chips_layout.addWidget(chip_btn)

        self._btn_chip_ue.clicked.connect(lambda: self._insert_chip("@ue "))
        self._btn_chip_actor.clicked.connect(lambda: self._insert_chip("@actor "))
        self._btn_chip_asset.clicked.connect(lambda: self._insert_chip("@asset "))
        self._btn_cmd_build.clicked.connect(lambda: self._insert_chip("/build "))
        self._btn_cmd_clear.clicked.connect(self._clear_chat)

        chips_layout.addStretch()
        root.addWidget(self._chips_widget)

        # Input row
        input_widget = QWidget()
        input_widget.setObjectName("panel_action_bar")
        input_widget.setStyleSheet("background: #0d0b14; border-top: 1px solid #231c34;")
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(12, 10, 12, 10)
        input_layout.setSpacing(10)

        self._input = QPlainTextEdit()
        self._input.setObjectName("chat_input")
        self._input.setPlaceholderText(
            "Describe what you want to build or fix… type /build, /ue, /compact or use @actor, @asset (Enter to send)"
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
        self._agent.plan_received.connect(self._on_plan_received)
        self._agent.tool_called.connect(self._on_tool_called)
        self._agent.tool_result.connect(self._on_tool_result)
        self._agent.file_changed.connect(self._on_file_changed)
        self._agent.diff_pending.connect(self._on_diff_pending)
        self._agent.error_occurred.connect(self._on_error)
        self._agent.task_done.connect(self._on_done)
        self._model_combo.currentTextChanged.connect(self._on_model_changed)

    def _init_session(self) -> None:
        """Create initial session asynchronously."""
        try:
            t_mode = "planning" if self.task_mode_combo.currentText() == "Planning" else "fast"
            a_prof = self.autonomy_combo.currentText().lower().replace("-", "_")
            self._session_id = self._agent.create_session(
                name="Default Session",
                model_name=get_settings().model_for("chat"),
                provider_type="ollama",
                task_mode=t_mode,
                autonomy_profile=a_prof,
            )
            self._show_start_screen()
            self._status_bar.set_ready()
            QTimer.singleShot(500, self._load_models)
        except Exception as exc:
            self._add_error_message(f"Failed to initialise session: {exc}")

    def _load_models(self) -> None:
        try:
            models = self._agent.list_models()
        except Exception:
            models = []
        self._model_combo.blockSignals(True)
        try:  # always unblock: an exception here used to leave the combo's signals blocked for the session
            self._model_combo.clear()
            for m in models:
                self._model_combo.addItem(m.get("id", m.get("name", "unknown")))
            if self._model_combo.count() == 0 and self._current_model:
                # Ollama offline: show the configured model instead of an empty box.
                self._model_combo.addItem(self._current_model)
                self._model_combo.setToolTip("Model list unavailable (Ollama offline); showing the configured model")
            else:
                self._model_combo.setToolTip("")
            idx = self._model_combo.findText(self._current_model)
            if idx >= 0:
                self._model_combo.setCurrentIndex(idx)
            elif self._model_combo.count() > 0:
                self._current_model = self._model_combo.itemText(0)
        finally:
            self._model_combo.blockSignals(False)
        self.model_changed.emit(self._current_model)
        names = [m.get("id", m.get("name", "unknown")) for m in models]
        if not names and self._current_model:
            names = [self._current_model]
        self.models_loaded.emit(names)

    def set_model_server_available(self, available: bool) -> None:
        """Called with the main window's real Ollama health check. (list_models() returns the configured roster
        even when the server is down, so it cannot tell.) Posts one notice per outage and one on recovery."""
        if not available and not getattr(self, "_offline_notice_shown", False):
            self._offline_notice_shown = True
            self._add_system_message(
                "⚠️ **Ollama is not reachable**, so chat and game generation are paused.\n\n"
                "Start it with `ollama serve` (or the Ollama app), then press **Check Ollama** in the toolbar.")
        elif available and getattr(self, "_offline_notice_shown", False):
            self._offline_notice_shown = False
            self._add_system_message("✅ **Ollama is reachable again.** You can continue.")

    def _setup_unreal_sync(self) -> None:
        """Poll unreal_context.json periodically to update UI badges and chips."""
        self._ue_sync_timer = QTimer(self)
        self._ue_sync_timer.setInterval(2500)
        self._ue_sync_timer.timeout.connect(self._check_unreal_context_sync)
        self._ue_sync_timer.start()
        # Initial check
        QTimer.singleShot(400, self._check_unreal_context_sync)

    def _check_unreal_context_sync(self) -> None:
        if not self._workspace:
            return
        # Re-read only when the context file changed: one stat() per poll instead of read + parse + validate.
        try:
            st = UnrealEditorContext.context_path(self._workspace).stat()
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            stamp = None
        if stamp is not None and stamp == getattr(self, "_ue_ctx_stamp", None):
            return
        self._ue_ctx_stamp = stamp
        try:
            ctx = load_unreal_context(self._workspace)
            if not ctx:
                self._status_bar.set_unreal_status(False)
                self.unreal_status_changed.emit(False, "", "")
                return
            last_sync = ctx.get("last_sync", "")
            project_name = ctx.get("project_name", "")
            active_asset = ctx.get("active_asset", "")
            is_connected = bool(project_name or active_asset)
            self._status_bar.set_unreal_status(is_connected, project_name, active_asset)
            self.unreal_status_changed.emit(is_connected, project_name, active_asset)
            if last_sync and last_sync != self._last_unreal_sync:
                self._last_unreal_sync = last_sync
        except Exception:
            pass

    def _insert_chip(self, tag: str) -> None:
        """Insert a context chip or command into the input cursor position."""
        cursor = self._input.textCursor()
        cursor.insertText(tag)
        self._input.setTextCursor(cursor)
        self._input.setFocus()

    def _handle_slash_command(self, text: str) -> bool:
        """Process Antigravity / Claude Code style slash commands."""
        stripped = text.strip()
        cmd = stripped.split()[0].lower() if stripped.startswith("/") else ""

        if not cmd:
            return False

        if cmd == "/clear":
            self._input.clear()
            self._clear_chat()
            return True

        if cmd == "/new":
            self._input.clear()
            self._new_session()
            return True

        if cmd == "/game":
            self._input.clear()
            from ...pipeline.spec_from_prompt import expand_game_flags
            idea = expand_game_flags(stripped[len("/game"):].strip())
            self._add_bubble("user", text)
            if not idea:
                self._add_system_message("Usage: `/game <describe the game>` — e.g. `/game gomoku against the computer`.")
                return True
            try:
                from ...backend.tools.game_tools import GameTools
                rec = GameTools(Path(self._workspace or ".")).propose_create_game(
                    f"create a {idea}" + ("" if "game" in idea.lower() else " game"), session_id=self._session_id)
            except Exception as exc:
                self._add_error_message(f"Game planner failed: {exc}")
                return True
            if rec and rec.get("approval_id"):
                self._add_bubble("assistant", rec["plan_text"])
                self._add_approval_card(rec)
            else:
                self._add_error_message("Could not plan that game.")
            return True

        if cmd == "/ue" or cmd == "/context":
            self._input.clear()
            self._add_bubble("user", text)
            if self._workspace:
                ctx = load_unreal_context(self._workspace)
                if ctx:
                    summary = (
                        f"🎮 **Unreal Editor Active Context**\n\n"
                        f"- **Project:** `{ctx.get('project_name', 'None')}`\n"
                        f"- **Engine Version:** `{ctx.get('engine_version', 'None')}`\n"
                        f"- **Selected Actor:** `{ctx.get('selected_actor', 'None')}`\n"
                        f"- **Active Asset:** `{ctx.get('active_asset', 'None')}`\n"
                        f"- **Open Assets:** {len(ctx.get('open_assets', []))} tracked\n"
                        f"- **Last Sync:** `{ctx.get('last_sync', 'None')}`"
                    )
                else:
                    summary = (
                        "🎮 **Unreal Engine Context:** Disconnected\n"
                        "No active `.gameforge/unreal_context.json` found in workspace. "
                        "Launch the GameForge Unreal plugin to auto-link."
                    )
            else:
                summary = "🎮 No workspace root configured."
            self._add_bubble("assistant", summary)
            self.slash_command_executed.emit(cmd, stripped)
            return True

        if cmd == "/build":
            self._input.clear()
            self._add_bubble("user", text)
            self._add_bubble("tool", "⚙️ **Executing `/build`** — Forwarding staged build request...")
            self.slash_command_executed.emit(cmd, stripped)
            return True

        if cmd in ("/diff", "/terminal", "/explorer"):
            self._input.clear()
            self._add_bubble("user", text)
            self._add_bubble("tool", f"📂 Toggling `{cmd[1:]}` view...")
            self.slash_command_executed.emit(cmd, stripped)
            return True

        if cmd == "/export":
            self._input.clear()
            self._add_bubble("user", text)
            if self._workspace and self._session_id:
                try:
                    from ...backend.session_manager import SessionManager
                    sm = SessionManager(self._workspace)
                    export_path = sm.export_session(self._session_id)
                    self._add_bubble(
                        "assistant",
                        f"📄 **Session Export Complete**\n\n"
                        f"- **Format:** Markdown transcript\n"
                        f"- **Location:** `{export_path}`\n\n"
                        f"Saved complete multi-turn history and tool executions."
                    )
                except Exception as exc:
                    self._add_bubble("assistant", f"❌ Failed to export session: {exc}")
            else:
                self._add_bubble("assistant", "⚠️ No active session or workspace to export.")
            return True

        if cmd == "/resume":
            self._input.clear()
            self._add_bubble("user", text)
            parts = stripped.split(maxsplit=1)
            target_id = parts[1].strip() if len(parts) > 1 else ""
            if self._workspace:
                try:
                    from ...backend.session_manager import SessionManager
                    sm = SessionManager(self._workspace)
                    if target_id:
                        sess = sm.get_session(target_id)
                        if sess:
                            self._session_id = sess.session_id
                            self._clear_chat()
                            for msg in sess.messages:
                                self._add_bubble(msg.role, msg.content)
                            self._add_bubble("assistant", f"🔄 **Resumed Session:** `{sess.name}` (`{sess.session_id}`)")
                        else:
                            self._add_bubble("assistant", f"❌ Session `{target_id}` not found.")
                    else:
                        sessions = sm.list_sessions()
                        if sessions:
                            lines = ["### 📂 Saved Sessions (use `/resume <id>` to switch):\n"]
                            for s in sessions[:5]:
                                lines.append(f"- `{s['session_id'][:8]}...` — **{s['name']}** ({s['message_count']} msgs, model: {s['model_name']})")
                            self._add_bubble("assistant", "\n".join(lines))
                        else:
                            self._add_bubble("assistant", "ℹ️ No saved sessions found in `.gameforge/sessions`.")
                except Exception as exc:
                    self._add_bubble("assistant", f"❌ Error loading sessions: {exc}")
            return True

        if cmd == "/model":
            self._input.clear()
            self._add_bubble("user", text)
            parts = stripped.split(maxsplit=1)
            if len(parts) > 1:
                target_model = parts[1].strip()
                self.set_model(target_model)
                self._add_bubble("assistant", f"🧠 Active model set to: `{target_model}`")
            else:
                current = self._model_combo.currentText()
                self._add_bubble("assistant", f"🧠 Current active model: `{current}`\nTo change, use `/model <name>`.")
            return True

        if cmd == "/permissions":
            self._input.clear()
            self._add_bubble("user", text)
            self._add_bubble(
                "assistant",
                "### 🛡️ GameForge Interaction & Permission Policies\n\n"
                "- **Tier 1 (Read-Only / Plan):** Inspect workspace and engine without modifications.\n"
                "- **Tier 2 (Ask Before Risky Actions - Active Default):** Read tools run automatically; file edits (`propose_edit`), builds, and commands require reviewed approval.\n"
                "- **Tier 3 (Workspace Edit):** Pre-approved reversible edits within workspace boundaries with atomic rollback.\n"
                "- **Tier 4 (Autonomous Safe Work):** Fully autonomous read/plan/propose with human-in-the-loop diff review."
            )
            return True

        if cmd == "/plan":
            self._input.clear()
            self._add_bubble("user", text)
            self._add_bubble(
                "assistant",
                "📋 **Plan Mode:** Active. GameForge will inspect the project, formulate a structured implementation plan, and verify dependencies before proposing changes."
            )
            return True

        if cmd in ("/undo", "/rollback"):
            self._input.clear()
            self._add_bubble("user", text)
            self._add_bubble("tool", "↩️ **Executing `/undo`** — Requesting rollback of last applied diff...")
            self.slash_command_executed.emit("/undo", stripped)
            return True

        if cmd == "/test":
            self._input.clear()
            self._add_bubble("user", text)
            self._add_bubble("tool", "🧪 **Executing `/test`** — Running project test suite...")
            self.slash_command_executed.emit(cmd, stripped)
            return True

        if cmd == "/help":
            self._input.clear()
            self._add_bubble("user", text)
            help_text = (
                "### 🎮 GameForge IDE Slash Commands & Context Chips\n\n"
                "- `/build` — Trigger Unreal Engine staged compilation\n"
                "- `/ue` or `/context` — Display live Unreal Editor sync state\n"
                "- `/clear` — Clear the current chat view\n"
                "- `/new` — Initialize a new clean agent session\n"
                "- `/resume [id]` — List or resume saved sessions\n"
                "- `/export` — Export conversation transcript to markdown\n"
                "- `/model [name]` — Inspect or switch active model\n"
                "- `/permissions` — Show security and permission tiers\n"
                "- `/plan` — Toggle structured planning mode\n"
                "- `/undo` — Rollback the last applied edit\n"
                "- `/diff` — Toggle diff review panel\n"
                "- `/terminal` — Toggle integrated PowerShell terminal\n"
                "- `/explorer` — Toggle file explorer dock\n"
                "- `/game <idea>` — Plan a complete Unreal game and show its approval card\n"
                "- `/test` — Execute test suite verification\n"
                "- `@ue`, `@actor`, `@asset` — Context expansion tokens in prompts\n"
            )
            self._add_bubble("assistant", help_text)
            return True

        return False


    # ── Slots ─────────────────────────────────────────────────────────────────


    def _show_start_screen(self) -> None:
        if self._start_screen is None:
            self._start_screen = _StartScreen(self._workspace, parent=self)
            self._start_screen.make_game_clicked.connect(self._on_start_make_game)
            self._start_screen.ask_question_clicked.connect(self._on_start_ask_question)
            self._start_screen.open_project_clicked.connect(self.open_project_requested.emit)
            self._start_screen.play_game_clicked.connect(self._on_start_play_game)
            self._msg_layout.insertWidget(0, self._start_screen)
        self._start_screen.show()

    def _hide_start_screen(self) -> None:
        if self._start_screen is not None:
            self._start_screen.hide()

    def _on_start_make_game(self, text: str = "") -> None:
        if text:
            self._input.setPlainText(text)
        else:
            self._input.setPlainText("/game ")
        self._input.setFocus()
        cursor = self._input.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._input.setTextCursor(cursor)

    def _on_start_ask_question(self) -> None:
        self._input.setFocus()
        self._input.setPlaceholderText("Ask the assistant anything about your game…")

    def _on_start_play_game(self, game_id: str) -> None:
        if game_id == "__view_mission__":
            self.slash_command_executed.emit("mission", "")
        else:
            self._on_play_game(game_id)

    def send_prompt(self, prompt: str) -> bool:
        """Send a prompt directly through the active assistant session."""
        if not prompt.strip() or not self._session_id:
            return False
        if self._agent.is_busy:
            return False
        self._hide_start_screen()
        self._last_prompt = prompt
        self._add_bubble("user", prompt)
        self._active_bubble = self._add_bubble("assistant", "")
        self._btn_send.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._status_bar.set_busy("PLANNING")
        ok = self._agent.send(self._session_id, prompt)
        if not ok:
            self._btn_send.setEnabled(True)
            self._btn_stop.setEnabled(False)
            self._status_bar.set_ready()
        return ok

    _on_prompt_submitted = send_prompt  # Compatibility alias for studio routing

    @Slot()
    def _on_send(self) -> None:
        # Preserve the exact composer payload; whitespace-only detection must
        # not mutate copied code, indentation, or deliberate boundary spaces.
        prompt = self._input.toPlainText()
        if not prompt.strip() or not self._session_id:
            return

        # Check slash commands first
        if prompt.strip().startswith("/"):
            if self._handle_slash_command(prompt):
                return

        if self._agent.is_busy:
            self._status_bar.set_busy(
                "STOPPING PREVIOUS TASK" if self._agent.is_stopping else "TASK ALREADY RUNNING"
            )
            return

        self._input.clear()
        self.send_prompt(prompt)

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
        if "<think>" in token or "</think>" in token:
            return
        self._tokens_streamed_in_turn = True
        self._finalize_status_activity()

        if not self._active_bubble:
            self._token_buffer += token
            stripped = self._token_buffer.lstrip()
            # Suppress raw JSON tool call leaks and shell commands from appearing in assistant bubbles during streaming
            if stripped.startswith(("{", "```json", "```\n{", "[TOOL_CALL]", "<tool_call>", "cat >", "mkdir -p", "mkdir ", "ls -", "dir ")):
                if self._is_raw_tool_json(self._token_buffer):
                    return
                if len(stripped) < 40:
                    return
            self._active_bubble = self._add_bubble("assistant", "")
            self._active_bubble.append_token(self._token_buffer)
            self._token_buffer = ""
        else:
            if self._is_raw_tool_json(self._active_bubble._raw_text + token):
                self._remove_bubble(self._active_bubble)
                self._active_bubble = None
                return
            was_at_bottom = self._is_scrolled_to_bottom()
            self._active_bubble.append_token(token)
            if was_at_bottom:
                self._scroll_to_bottom()

    # ── Approval-gated actions (create_game, editor ops, builds) ───────────────
    def _add_open_design_card(self, card_data: dict) -> QFrame:
        prompt = card_data.get("prompt", "")
        mode = card_data.get("mode", "create")
        frame = QFrame(self)
        frame.setObjectName("openDesignCard")
        frame.setStyleSheet(
            f"QFrame#openDesignCard {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.ACCENT_PRIMARY};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 12px;"
            f"}}"
        )
        layout = QVBoxLayout(frame)
        project_name = card_data.get("project", "")
        if project_name:
            title_text = f"Game Update: {project_name}"
        else:
            title_text = "Game Design Request" if mode == "create" else "Design Change Request"
        title = QLabel(title_text, frame)
        title.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        p_lbl = QLabel(f'"{prompt}"', frame)
        p_lbl.setWordWrap(True)
        p_lbl.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-style: italic;")
        layout.addWidget(p_lbl)

        if mode == "change":
            msg_lbl = QLabel("Edit the design to apply this change", frame)
            msg_lbl.setStyleSheet(f"color: {tokens.ACCENT_WARNING}; font-size: 11px;")
            layout.addWidget(msg_lbl)

        btn = QPushButton("Open in Design", frame)
        btn.setObjectName("btnOpenInDesign")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton#btnOpenInDesign {{"
            f"  background-color: {tokens.ACCENT_PRIMARY}; color: {tokens.TEXT_PRIMARY};"
            f"  border: none; border-radius: {tokens.RADIUS}px; padding: 6px 12px; font-weight: 600;"
            f"}}"
        )
        btn.clicked.connect(lambda: self.openDesignRequested.emit(prompt))
        layout.addWidget(btn)

        self._msg_layout.insertWidget(self._msg_layout.count() - 1, frame)
        self._scroll_to_bottom()
        return frame

    def _add_approval_card(self, approval: dict) -> ApprovalCard:
        card = ApprovalCard(approval)
        card.approve_clicked.connect(self._on_approve_action)
        card.reject_clicked.connect(self._on_reject_action)
        card.play_clicked.connect(self._on_play_game)
        card.cancel_clicked.connect(self._runner.cancel)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, card)
        self._cards[approval["approval_id"]] = card
        self._scroll_to_bottom()
        return card

    def _restore_pending_approvals(self) -> None:
        """Pending approvals survive restarts and never execute without a fresh click."""
        try:
            from ...backend.tools.game_tools import ApprovalStore
            pending = ApprovalStore(Path(self._workspace or ".")).list_pending()
        except Exception:
            return
        for rec in pending:
            if rec["approval_id"] not in self._cards:
                self._add_system_message("Restored a pending approval from a previous session.")
                self._add_approval_card(rec)

    @Slot(str)
    def _on_approve_action(self, approval_id: str) -> None:
        card = self._cards.get(approval_id)
        if self._runner.approve(approval_id) and card:
            card.set_running()
            self._status_bar.set_busy("BUILDING")

    @Slot(str)
    def _on_reject_action(self, approval_id: str) -> None:
        self._runner.reject(approval_id)

    @Slot(str, str, dict)
    def _on_action_progress(self, approval_id: str, kind: str, data: dict) -> None:
        card = self._cards.get(approval_id)
        if card:
            card.on_progress(kind, data)

    @Slot(dict)
    def show_approval(self, approval: dict) -> None:
        """Bring a pending approval (e.g. from Mission Control) into the chat as a card."""
        card = self._cards.get(approval.get("approval_id"))
        if card is None:
            card = self._add_approval_card(approval)
        self._scroll_area.ensureWidgetVisible(card)

    @Slot(str, dict)
    def _on_action_finished(self, approval_id: str, result: dict) -> None:
        self.action_finished.emit(approval_id, result)
        card = self._cards.get(approval_id)
        if card:
            card.on_finished(result)
        self._status_bar.set_ready()
        if result.get("status") == "SUCCESS" and result.get("exe"):
            self._add_bubble("assistant", "✅ **Your game is ready.** Every acceptance check passed in the real engine "
                                          "(compile, automation tests, packaged play-test with screenshot). "
                                          "Press **▶ Play game** on the card to play it.")

    @Slot(str)
    def _on_play_game(self, exe: str) -> None:
        try:
            from ...backend.tools.gateway import ToolGateway
            res = ToolGateway(Path(self._workspace or ".")).execute_tool("play_game", {"exe": exe}, approval_granted=True)
            if res.get("status") != "SUCCESS":
                self._add_error_message(res.get("error", "could not launch game"))
        except Exception as exc:
            self._add_error_message(f"could not launch game: {exc}")

    @staticmethod
    def _is_raw_tool_json(text: str) -> bool:
        t = text.strip()
        if not t:
            return False
        if t.startswith("```json") and t.endswith("```"):
            t = t[7:-3].strip()
        elif t.startswith("```") and t.endswith("```"):
            t = t[3:-3].strip()
        if t.startswith("{") and (t.endswith("}") or '"tool"' in t or '"tool_name"' in t):
            for key in ('"tool"', '"tool_name"', '"function"', '"name"'):
                if key in t:
                    return True
        if t.startswith("<tool_call>") or t.startswith("[TOOL_CALL]"):
            return True
        if t.startswith(("cat >", "mkdir -p", "mkdir ")) or re.match(r"^(?:ls|dir)\b", t):
            return True
        if "<think>" in t or "</think>" in t:
            subbed = re.sub(r"</?think>", "", t).strip()
            if not subbed or re.match(r"^(?:ls|dir|cat|mkdir)\b", subbed):
                return True
        return False

    def _remove_bubble(self, bubble: _MessageBubble) -> None:
        if bubble is not None:
            self._msg_layout.removeWidget(bubble)
            bubble.setVisible(False)
            bubble.deleteLater()

    def _finalize_status_activity(self) -> None:
        if getattr(self, "_active_status_item", None):
            try:
                self._active_status_item.finalise()
            except Exception:
                pass
            self._active_status_item = None

    @Slot(str, dict)
    def _on_status(self, status: str, _meta: dict) -> None:
        if self._ignore_active_task_events or self._agent.is_stopping:
            return
        if status == "WAITING_APPROVAL" and isinstance(_meta.get("approval"), dict):
            if self._active_bubble:
                if not self._active_bubble.has_tokens() or self._is_raw_tool_json(self._active_bubble._raw_text):
                    self._remove_bubble(self._active_bubble)
                else:
                    self._active_bubble.finalise()
                self._active_bubble = None
            self._finalize_status_activity()
            self._add_approval_card(_meta["approval"])
        elif status == "READY" and isinstance(_meta.get("card"), dict):
            if self._active_bubble:
                if not self._active_bubble.has_tokens() or self._is_raw_tool_json(self._active_bubble._raw_text):
                    self._remove_bubble(self._active_bubble)
                else:
                    self._active_bubble.finalise()
                self._active_bubble = None
            self._finalize_status_activity()
            # In GameForge 1.0, all tasks execute autonomously in chat; retired open_design cards are omitted
        elif status in ("THINKING", "PLANNING", "REPAIRING"):
            if self._active_bubble:
                if not self._active_bubble.has_tokens() or self._is_raw_tool_json(self._active_bubble._raw_text):
                    self._remove_bubble(self._active_bubble)
                else:
                    self._active_bubble.finalise()
                self._active_bubble = None
            if not getattr(self, "_active_status_item", None):
                s_item = StatusActivityItem(status.lower(), _meta, parent=self)
                self._msg_layout.insertWidget(self._msg_layout.count() - 1, s_item)
                self._active_status_item = s_item
                self._scroll_to_bottom()
            else:
                self._active_status_item.meta.update(_meta)
                self._active_status_item.status_kind = status.lower()
                self._active_status_item._refresh_display()
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
        self._token_buffer = ""
        if self._active_bubble:
            from ...backend.agent.runtime import AgentRuntime
            clean_text = AgentRuntime._clean_narrative_text(self._active_bubble._raw_text)
            if not clean_text or self._is_raw_tool_json(self._active_bubble._raw_text):
                self._remove_bubble(self._active_bubble)
            else:
                self._active_bubble._render_text(clean_text)
                self._active_bubble.finalise()
            self._active_bubble = None
        self._finalize_status_activity()
        if getattr(self, "_active_tool_item", None):
            try:
                self._active_tool_item.finalise()
            except Exception:
                pass
            self._active_tool_item = None
        item = ToolActivityItem(tool_name, args, parent=self)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, item)
        self._active_tool_item = item
        self._scroll_to_bottom()

    @Slot(str, dict)
    def _on_tool_result(self, tool_name: str, result: dict) -> None:
        if self._ignore_active_task_events or self._agent.is_stopping:
            return
        if getattr(self, "_active_tool_item", None) and self._active_tool_item.tool_name == tool_name:
            self._active_tool_item.set_result(result)
            self._active_tool_item = None
        else:
            item = ToolActivityItem(tool_name, {}, result=result, parent=self)
            self._msg_layout.insertWidget(self._msg_layout.count() - 1, item)
        # Reset active bubble; continued narrative tokens will create bubble lazily
        self._active_bubble = None
        self._scroll_to_bottom()

    @Slot(dict)
    def _on_plan_received(self, plan_data: dict) -> None:
        if self._ignore_active_task_events or self._agent.is_stopping:
            return
        self._tokens_streamed_in_turn = False
        if self._active_bubble:
            if not self._active_bubble.has_tokens() or self._is_raw_tool_json(self._active_bubble._raw_text):
                self._remove_bubble(self._active_bubble)
            else:
                self._active_bubble.finalise()
            self._active_bubble = None

        plan_id = plan_data.get("plan_id", "")
        active_card = getattr(self, "_active_plan_card", None)
        if plan_id and plan_id in self._plan_cards:
            self._plan_cards[plan_id].update_plan(plan_data)
            self._active_plan_card = self._plan_cards[plan_id]
        elif active_card is not None and not getattr(active_card, "_is_completed", False):
            active_card.update_plan(plan_data)
            if plan_id:
                self._plan_cards[plan_id] = active_card
        else:
            card = PlanCard(plan_data, parent=self)
            card.proceed_clicked.connect(self._on_plan_proceed)
            card.revision_requested.connect(self._on_plan_revision)
            self._msg_layout.insertWidget(self._msg_layout.count() - 1, card)
            self._active_plan_card = card
            if plan_id:
                self._plan_cards[plan_id] = card

        self.plan_received.emit(plan_data)
        self._scroll_to_bottom()

    @Slot(str)
    def _on_plan_proceed(self, plan_id: str) -> None:
        if self._agent.is_busy:
            return
        self.send_prompt("proceed")

    @Slot(str, str)
    def _on_plan_revision(self, plan_id: str, revision_text: str) -> None:
        if self._agent.is_busy or not revision_text.strip():
            return
        self.send_prompt(revision_text.strip())

    @Slot(str, dict)
    def _on_file_changed(self, content: str, meta: dict) -> None:
        if self._ignore_active_task_events or self._agent.is_stopping:
            return
        notif = FileChangedNotification(content, meta, parent=self)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, notif)
        self.file_changed.emit(content, meta)
        self._scroll_to_bottom()

    @Slot(str, dict)
    def _on_diff_pending(self, diff_id: str, meta: dict) -> None:
        if self._ignore_active_task_events or self._agent.is_stopping:
            return
        if self._active_bubble:
            if not self._active_bubble.has_tokens() or self._is_raw_tool_json(self._active_bubble._raw_text):
                self._remove_bubble(self._active_bubble)
            else:
                self._active_bubble.finalise()
            self._active_bubble = None

        card = DiffApprovalCard(diff_id, meta, parent=self)
        card.diff_approved.connect(lambda did: self._agent.resume_after_diff(self._session_id, did, approved=True))
        card.diff_rejected.connect(lambda did: self._agent.resume_after_diff(self._session_id, did, approved=False))
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, card)
        self._cards[diff_id] = card

        self.diff_pending.emit(diff_id, meta)
        self._scroll_to_bottom()

    def _on_task_mode_changed(self, text: str) -> None:
        val = "planning" if text.lower() == "planning" else "fast"
        if self._session_id and hasattr(self._agent, "set_session_mode"):
            self._agent.set_session_mode(self._session_id, task_mode=val)
        self.task_mode_changed.emit(val)

    def _on_autonomy_changed(self, text: str) -> None:
        prof_map = {"manual": "manual", "auto-edit": "auto_edit", "auto_edit": "auto_edit", "agentic": "agentic"}
        val = prof_map.get(text.lower(), "agentic")
        if self._session_id and hasattr(self._agent, "set_session_mode"):
            self._agent.set_session_mode(self._session_id, autonomy_profile=val)
        self.autonomy_changed.emit(val)

    def set_task_mode(self, mode: str) -> None:
        normalized = "Planning" if mode.lower() == "planning" else "Fast"
        val = "planning" if mode.lower() == "planning" else "fast"
        self.task_mode_combo.blockSignals(True)
        self.task_mode_combo.setCurrentText(normalized)
        self.task_mode_combo.blockSignals(False)
        if self._session_id and hasattr(self._agent, "set_session_mode"):
            self._agent.set_session_mode(self._session_id, task_mode=val)

    def set_autonomy_profile(self, profile: str) -> None:
        prof_map = {"manual": "Manual", "auto_edit": "Auto-Edit", "auto-edit": "Auto-Edit", "agentic": "Agentic"}
        normalized = prof_map.get(profile.lower(), "Agentic")
        val = "auto_edit" if "auto" in profile.lower() else ("manual" if profile.lower() == "manual" else "agentic")
        self.autonomy_combo.blockSignals(True)
        self.autonomy_combo.setCurrentText(normalized)
        self.autonomy_combo.blockSignals(False)
        if self._session_id and hasattr(self._agent, "set_session_mode"):
            self._agent.set_session_mode(self._session_id, autonomy_profile=val)

    @Slot(str)
    def _on_error(self, error: str) -> None:
        self._tokens_streamed_in_turn = False
        if getattr(self, "_active_tool_item", None):
            self._active_tool_item.finalise()
            self._active_tool_item = None
        self._finalize_status_activity()
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
        if getattr(self, "_active_tool_item", None):
            self._active_tool_item.finalise()
            self._active_tool_item = None
        self._finalize_status_activity()
        if self._ignore_active_task_events:
            self._ignore_active_task_events = False
            self._active_bubble = None
            self._token_buffer = ""
            self._btn_send.setEnabled(True)
            self._btn_stop.setEnabled(False)
            self._status_bar.set_ready()
            return

        # Flush any remaining non-tool buffer
        if self._token_buffer:
            if not self._is_raw_tool_json(self._token_buffer):
                if not self._active_bubble:
                    self._active_bubble = self._add_bubble("assistant", "")
                self._active_bubble.append_token(self._token_buffer)
            self._token_buffer = ""

        if self._active_bubble:
            if not self._active_bubble.has_tokens() and _full_text and not self._tokens_streamed_in_turn:
                from ...backend.agent.runtime import AgentRuntime
                clean_text = AgentRuntime._clean_narrative_text(_full_text.strip())
                if clean_text and not self._is_raw_tool_json(clean_text):
                    self._active_bubble.append_token(clean_text)
            from ...backend.agent.runtime import AgentRuntime
            clean = AgentRuntime._clean_narrative_text(self._active_bubble._raw_text)
            if not clean or self._is_raw_tool_json(self._active_bubble._raw_text):
                self._remove_bubble(self._active_bubble)
            else:
                self._active_bubble._render_text(clean)
                self._active_bubble.finalise()
            self._active_bubble = None
        elif _full_text and not self._tokens_streamed_in_turn:
            from ...backend.agent.runtime import AgentRuntime
            clean_text = AgentRuntime._clean_narrative_text(_full_text.strip())
            if clean_text and not self._is_raw_tool_json(clean_text):
                b = self._add_bubble("assistant", clean_text)
                b.finalise()
        self._tokens_streamed_in_turn = False
        self._token_buffer = ""
        self._btn_send.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._status_bar.set_ready()

    @Slot(str)
    def _on_model_changed(self, model_name: str) -> None:
        if not model_name:
            return
        self._current_model = model_name
        self._status_bar.set_model(model_name)
        if self._session_id:
            try:
                self._agent.set_session_model(self._session_id, model_name)
            except Exception:
                pass
        self.model_changed.emit(model_name)

    def set_model(self, model_name: str) -> None:
        """Programmatically switch active model and synchronize UI."""
        if not model_name:
            return
        self._current_model = model_name
        self._status_bar.set_model(model_name)
        if self._session_id:
            try:
                self._agent.set_session_model(self._session_id, model_name)
            except Exception:
                pass
        idx = self._model_combo.findText(model_name)
        self._model_combo.blockSignals(True)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        else:
            self._model_combo.addItem(model_name)
            self._model_combo.setCurrentText(model_name)
        self._model_combo.blockSignals(False)
        self.model_changed.emit(model_name)

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
        if getattr(self, "_scroll_pending", False):
            return
        self._scroll_pending = True

        def _do_scroll():
            self._scroll_pending = False
            try:
                if hasattr(self, "_scroll_area") and self._scroll_area:
                    sb = self._scroll_area.verticalScrollBar()
                    if sb:
                        sb.setValue(sb.maximum())
            except (RuntimeError, Exception):
                pass

        QTimer.singleShot(20, _do_scroll)

    def _clear_chat(self) -> None:
        self._token_buffer = ""
        self._tokens_streamed_in_turn = False
        try:
            if self._agent.is_busy:
                self._ignore_active_task_events = True
                self._agent.stop()
                self._active_bubble = None
        except Exception:
            pass
        for i in reversed(range(self._msg_layout.count())):
            item = self._msg_layout.itemAt(i)
            if item and item.widget():
                if item.widget() is getattr(self, "_start_screen", None):
                    continue
                w = item.widget()
                self._msg_layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
        self._active_bubble = None
        self._active_tool_item = None
        self._active_status_item = None
        self._active_plan_card = None
        self._plan_cards.clear()
        self._cards.clear()
        self._status_bar.set_ready()
        self._show_start_screen()

    def _new_session(self) -> None:
        self._token_buffer = ""
        self._tokens_streamed_in_turn = False
        self._active_tool_item = None
        self._active_status_item = None
        self._active_plan_card = None
        try:
            if self._agent.is_busy:
                self._ignore_active_task_events = True
                self._agent.stop()
                self._active_bubble = None
            t_mode = "planning" if self.task_mode_combo.currentText() == "Planning" else "fast"
            a_prof = self.autonomy_combo.currentText().lower().replace("-", "_")
            self._session_id = self._agent.create_session(
                name="New Session",
                model_name=self._current_model,
                provider_type="ollama",
                task_mode=t_mode,
                autonomy_profile=a_prof,
            )
            self._clear_chat()
            self._btn_send.setEnabled(not self._agent.is_busy)
            self._btn_stop.setEnabled(self._agent.is_busy)
            self._show_start_screen()
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
