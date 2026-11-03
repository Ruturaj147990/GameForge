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


class AssistantPanel(QWidget):
    """Studio UX collapsible assistant panel wrapping ChatPanel."""

    closeRequested = Signal()
    modelChanged = Signal(str)
    openDesignRequested = Signal(str)

    def __init__(
        self,
        chat_panel: QWidget,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("studioAssistantPanel")
        self.chat_panel = chat_panel
        if hasattr(self.chat_panel, "openDesignRequested"):
            self.chat_panel.openDesignRequested.connect(self.openDesignRequested)

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
        self.model_combo = QComboBox(header)
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
                max-width: 140px;
            }}
        """)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        h_layout.addWidget(self.model_combo)

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

    def set_models(self, models: List[str], current: Optional[str] = None) -> None:
        """Populate model selector dropdown."""
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for m in models:
            self.model_combo.addItem(m)
        if current and current in models:
            self.model_combo.setCurrentText(current)
        elif models:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.blockSignals(False)

    def _on_model_changed(self, text: str) -> None:
        if text:
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

    update_theme = refresh_icons
