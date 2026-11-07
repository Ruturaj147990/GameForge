"""AssistantPanel: Collapsible right assistant drawer wrapping ChatPanel (WI-4.3)."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..icons import icon
from ..styles import tokens


class _ModelComboBox(QComboBox):
    """ComboBox that automatically refreshes the available models before showing its popup."""

    def __init__(self, panel_ref: AssistantPanel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._panel_ref = panel_ref

    def showPopup(self) -> None:
        if self._panel_ref and hasattr(self._panel_ref, "_refresh_models_from_source"):
            self._panel_ref._refresh_models_from_source()
        super().showPopup()


class AssistantPanel(QWidget):
    """Studio UX collapsible assistant panel wrapping ChatPanel."""

    closeRequested = Signal()
    modelChanged = Signal(str)

    def __init__(
        self,
        chat_panel: QWidget,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("studioAssistantPanel")
        self.chat_panel = chat_panel

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar (40px)
        header = QWidget(self)
        header.setObjectName("assistantHeader")
        header.setFixedHeight(40)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 0, 8, 0)
        h_layout.setSpacing(8)

        title_lbl = QLabel("✦ Assistant", header)
        title_lbl.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: bold; font-size: 13px;")
        h_layout.addWidget(title_lbl)

        # Model selector
        self.model_combo = _ModelComboBox(self, header)
        self.model_combo.setObjectName("assistantModelCombo")
        self.model_combo.setAccessibleName("Assistant Model")
        self.model_combo.setToolTip("Select active assistant model")
        self.model_combo.setStyleSheet(f"""
            QComboBox {{
                background: {tokens.BG_SURFACE};
                color: {tokens.TEXT_PRIMARY};
                border: 1px solid {tokens.BORDER};
                border-radius: {tokens.RADIUS}px;
                padding: 2px 6px;
                font-size: 12px;
                min-width: 150px;
                max-width: 220px;
            }}
            QComboBox QAbstractItemView {{
                background: {tokens.BG_SURFACE};
                color: {tokens.TEXT_PRIMARY};
                selection-background-color: {tokens.BG_HOVER};
                selection-color: {tokens.TEXT_PRIMARY};
                border: 1px solid {tokens.BORDER};
                min-width: 260px;
            }}
        """)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        h_layout.addWidget(self.model_combo)

        # Connect model loaded updates from chat_panel if available
        if hasattr(self.chat_panel, "models_loaded"):
            self.chat_panel.models_loaded.connect(self._on_models_loaded)

        h_layout.addStretch(1)

        # New chat button
        self.new_btn = QToolButton(header)
        self.new_btn.setObjectName("assistantNewBtn")
        self.new_btn.setAccessibleName("New Chat Session")
        self.new_btn.setToolTip("Start new session")
        self.new_btn.setIcon(icon("build", role="secondary", size=14))
        self.new_btn.setFixedSize(26, 26)
        self.new_btn.clicked.connect(self._on_new_chat)
        h_layout.addWidget(self.new_btn)

        # Clear chat button
        self.clear_btn = QToolButton(header)
        self.clear_btn.setObjectName("assistantClearBtn")
        self.clear_btn.setAccessibleName("Clear Chat")
        self.clear_btn.setToolTip("Clear messages")
        self.clear_btn.setIcon(icon("cancel", role="secondary", size=14))
        self.clear_btn.setFixedSize(26, 26)
        self.clear_btn.clicked.connect(self._on_clear_chat)
        h_layout.addWidget(self.clear_btn)

        # Close button
        self.close_btn = QToolButton(header)
        self.close_btn.setObjectName("assistantCloseBtn")
        self.close_btn.setAccessibleName("Close Assistant Panel")
        self.close_btn.setToolTip("Close Assistant (Ctrl+J)")
        self.close_btn.setText("✕")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.clicked.connect(self.closeRequested.emit)
        h_layout.addWidget(self.close_btn)

        header.setStyleSheet(f"""
            QWidget#assistantHeader {{
                background: {tokens.BG_SURFACE};
                border-bottom: 1px solid {tokens.BORDER};
            }}
            QToolButton {{
                background: transparent;
                border: none;
                border-radius: 4px;
                color: {tokens.TEXT_SECONDARY};
            }}
            QToolButton:hover {{
                background: {tokens.BG_HOVER};
                color: {tokens.TEXT_PRIMARY};
            }}
        """)
        layout.addWidget(header)

        # Embed ChatPanel
        layout.addWidget(self.chat_panel, 1)

        self.setStyleSheet(f"""
            QWidget#studioAssistantPanel {{
                background: {tokens.BG_PANEL};
                border-left: 1px solid {tokens.BORDER};
            }}
        """)

    @property
    def task_mode_combo(self):
        return getattr(self.chat_panel, "task_mode_combo", None)

    @property
    def taskModeCombo(self):
        return getattr(self.chat_panel, "task_mode_combo", None)

    @property
    def permissions_mode_combo(self):
        return getattr(self.chat_panel, "permissions_mode_combo", None)

    @property
    def permissions_combo(self):
        return getattr(self.chat_panel, "permissions_mode_combo", None)

    @property
    def permissionsModeCombo(self):
        return getattr(self.chat_panel, "permissions_mode_combo", None)

    @property
    def autonomy_combo(self):
        return getattr(self.chat_panel, "autonomy_combo", None)

    @property
    def autonomy_profile_combo(self):
        return getattr(self.chat_panel, "autonomy_combo", None)

    @property
    def autonomyCombo(self):
        return getattr(self.chat_panel, "autonomy_combo", None)

    def _on_models_loaded(self, models: List[str]) -> None:
        """Slot triggered when ChatPanel discovers available models."""
        if models:
            self.set_models(models, getattr(self.chat_panel, "_current_model", None))

    def _refresh_models_from_source(self) -> None:
        """Query available models from agent service or chat panel."""
        agent = getattr(self.chat_panel, "_agent", None)
        if not agent and self.parent() and hasattr(self.parent(), "_agent"):
            agent = getattr(self.parent(), "_agent")
        if agent and hasattr(agent, "list_models"):
            try:
                models = [m.get("id", m.get("name", "unknown")) for m in agent.list_models()]
                if models:
                    self.set_models(models, self.model_combo.currentText())
            except Exception:
                pass

    def set_models(self, models: List[str], current: Optional[str] = None) -> None:
        """Populate model selector dropdown with tooltips and deduplication."""
        seen = set()
        unique_models = []
        for m in models:
            if m and m not in seen:
                seen.add(m)
                unique_models.append(m)

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for idx, m in enumerate(unique_models):
            self.model_combo.addItem(m)
            self.model_combo.setItemData(idx, m, Qt.ToolTipRole)

        target = current or (getattr(self.chat_panel, "_current_model", None) if hasattr(self, "chat_panel") else None)
        if target and target in unique_models:
            self.model_combo.setCurrentText(target)
        elif unique_models:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.setToolTip(f"Active Model: {self.model_combo.currentText()}")
        self.model_combo.blockSignals(False)

    def _on_model_changed(self, text: str) -> None:
        if text:
            self.model_combo.setToolTip(f"Active Model: {text}")
            # Sync with underlying chat panel if available
            if hasattr(self.chat_panel, "set_model"):
                self.chat_panel.set_model(text)
            self.modelChanged.emit(text)

    def _on_new_chat(self) -> None:
        if hasattr(self.chat_panel, "_new_session"):
            self.chat_panel._new_session()

    def _on_clear_chat(self) -> None:
        if hasattr(self.chat_panel, "_clear_chat"):
            self.chat_panel._clear_chat()

    def refresh_icons(self) -> None:
        """Refresh header button icons on theme change."""
        self.new_btn.setIcon(icon("build", role="secondary", size=14))
        self.clear_btn.setIcon(icon("cancel", role="secondary", size=14))

    def update_theme(self) -> None:
        self.setStyleSheet(f"""
            QWidget#studioAssistantPanel {{
                background: {tokens.BG_PANEL};
                border-left: 1px solid {tokens.BORDER};
            }}
        """)
        header = self.findChild(QWidget, "assistantHeader")
        if header:
            header.setStyleSheet(f"""
                QWidget#assistantHeader {{
                    background: {tokens.BG_SURFACE};
                    border-bottom: 1px solid {tokens.BORDER};
                }}
                QToolButton {{
                    background: transparent;
                    border: none;
                    border-radius: 4px;
                    color: {tokens.TEXT_SECONDARY};
                }}
                QToolButton:hover {{
                    background: {tokens.BG_HOVER};
                    color: {tokens.TEXT_PRIMARY};
                }}
            """)
        self.refresh_icons()
