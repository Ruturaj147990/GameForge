"""Toasts: Bottom-right notifications overlay for Studio UX (WI-4.3)."""

from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..icons import icon
from ..styles import tokens


class ToastCard(QFrame):
    """Single toast notification bubble."""

    dismissed = Signal(object)

    def __init__(
        self,
        kind: str,
        title: str,
        message: str,
        details_cb: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.setObjectName(f"toastCard_{kind}")
        self.setFixedWidth(320)

        border_color = (
            tokens.ACCENT_SUCCESS if kind == "success"
            else tokens.ACCENT_WARNING if kind == "warning"
            else tokens.ACCENT_ERROR if kind == "error"
            else tokens.ACCENT_PRIMARY
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 8, 10)
        layout.setSpacing(10)

        # Content column
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        lbl_title = QLabel(title, self)
        lbl_title.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: bold; font-size: 13px;")
        col.addWidget(lbl_title)

        if message:
            lbl_msg = QLabel(message, self)
            lbl_msg.setWordWrap(True)
            lbl_msg.setStyleSheet(f"color: {tokens.TEXT_SECONDARY}; font-size: 12px;")
            col.addWidget(lbl_msg)

        if details_cb is not None:
            btn_details = QPushButton("Details →", self)
            btn_details.setObjectName("toastDetailsBtn")
            btn_details.setCursor(Qt.PointingHandCursor)
            btn_details.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {tokens.ACCENT_HOVER};
                    border: none;
                    text-align: left;
                    font-size: 12px;
                    padding: 2px 0px;
                }}
                QPushButton:hover {{
                    text-decoration: underline;
                }}
            """)
            btn_details.clicked.connect(details_cb)
            col.addWidget(btn_details)

        layout.addLayout(col, 1)

        # Close button
        btn_close = QToolButton(self)
        btn_close.setText("✕")
        btn_close.setFixedSize(20, 20)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: none;
                color: {tokens.TEXT_SECONDARY};
                font-size: 11px;
            }}
            QToolButton:hover {{
                color: {tokens.TEXT_PRIMARY};
            }}
        """)
        btn_close.clicked.connect(self._dismiss)
        layout.addWidget(btn_close, alignment=Qt.AlignTop)

        self.setStyleSheet(f"""
            QFrame#{self.objectName()} {{
                background: {tokens.BG_SURFACE};
                border: 1px solid {tokens.BORDER};
                border-left: 4px solid {border_color};
                border-radius: {tokens.RADIUS}px;
            }}
        """)

        # Auto dismiss after 6 seconds unless kind == "error"
        if kind != "error":
            QTimer.singleShot(6000, self._dismiss)

    def _dismiss(self) -> None:
        self.dismissed.emit(self)


class ToastOverlay(QWidget):
    """Container anchored bottom-right showing at most 3 active toasts."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("studioToastOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignBottom | Qt.AlignRight)

        self._toasts: List[ToastCard] = []
        if parent:
            parent.installEventFilter(self)
        self._reposition()

    def eventFilter(self, watched, event) -> bool:
        if watched == self.parentWidget() and event.type() in (QEvent.Resize, QEvent.Show):
            self._reposition()
        return super().eventFilter(watched, event)

    def show_toast(
        self,
        kind: str,
        title: str,
        message: str = "",
        details_cb: Optional[Callable[[], None]] = None,
    ) -> ToastCard:
        """Add and display a toast, keeping at most 3 active."""
        if len(self._toasts) >= 3:
            oldest = self._toasts.pop(0)
            self._layout.removeWidget(oldest)
            oldest.deleteLater()

        toast = ToastCard(kind, title, message, details_cb, self)
        toast.dismissed.connect(self._on_toast_dismissed)
        self._toasts.append(toast)
        self._layout.addWidget(toast)
        self._reposition()
        self.raise_()
        return toast

    def info(self, title: str, message: str = "") -> ToastCard:
        return self.show_toast("info", title, message)

    def success(self, title: str, message: str = "") -> ToastCard:
        return self.show_toast("success", title, message)

    def warning(self, title: str, message: str = "") -> ToastCard:
        return self.show_toast("warning", title, message)

    def error(self, title: str, message: str = "", details_cb: Optional[Callable[[], None]] = None) -> ToastCard:
        return self.show_toast("error", title, message, details_cb)

    def _on_toast_dismissed(self, toast: ToastCard) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
            self._layout.removeWidget(toast)
            toast.deleteLater()
            self._reposition()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        pw = parent.width()
        ph = parent.height()
        w = 340
        h = max(60, len(self._toasts) * 90)
        self.setGeometry(pw - w - 20, ph - h - 30, w, h)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition()
