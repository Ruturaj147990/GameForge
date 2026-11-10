"""Toasts: Bottom-right notifications overlay for Studio UX (WI-4.3)."""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QResizeEvent
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
from ..styles.dark_theme import theme_stylesheet

logger = logging.getLogger(__name__)


class ToastCard(QFrame):
    """Single toast notification bubble."""

    dismissed = Signal(object)

    def __init__(
        self,
        kind: str,
        title: str,
        message: str = "",
        details_cb: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self._is_dismissed = False
        self._dismiss_timer: Optional[QTimer] = None
        self.setObjectName(f"toastCard_{kind}")
        self.setAccessibleName(f"Notification: {title}")
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
        lbl_title.setTextFormat(Qt.PlainText)
        lbl_title.setStyleSheet(theme_stylesheet(f"color: {tokens.TEXT_PRIMARY}; font-weight: bold; font-size: 13px;"))
        col.addWidget(lbl_title)

        if message:
            lbl_msg = QLabel(message, self)
            lbl_msg.setTextFormat(Qt.PlainText)
            lbl_msg.setWordWrap(True)
            lbl_msg.setStyleSheet(theme_stylesheet(f"color: {tokens.TEXT_SECONDARY}; font-size: 12px;"))
            col.addWidget(lbl_msg)

        if details_cb is not None:
            btn_details = QPushButton("Details →", self)
            btn_details.setObjectName("toastDetailsBtn")
            btn_details.setCursor(Qt.PointingHandCursor)
            btn_details.setAccessibleName("View details for notification")
            btn_details.setStyleSheet(theme_stylesheet(f"""
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
            """))
            def _safe_details() -> None:
                try:
                    details_cb()
                except Exception as exc:
                    logger.exception("Error in toast details callback: %s", exc)
            btn_details.clicked.connect(_safe_details)
            col.addWidget(btn_details)

        layout.addLayout(col, 1)

        # Close button
        btn_close = QToolButton(self)
        btn_close.setText("✕")
        btn_close.setFixedSize(20, 20)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setAccessibleName("Dismiss notification")
        btn_close.setStyleSheet(theme_stylesheet(f"""
            QToolButton {{
                background: transparent;
                border: none;
                color: {tokens.TEXT_SECONDARY};
                font-size: 11px;
            }}
            QToolButton:hover {{
                color: {tokens.TEXT_PRIMARY};
            }}
        """))
        btn_close.clicked.connect(self._dismiss)
        layout.addWidget(btn_close, alignment=Qt.AlignTop)

        self.setStyleSheet(theme_stylesheet(f"""
            QFrame#{self.objectName()} {{
                background: {tokens.BG_SURFACE};
                border: 1px solid {tokens.BORDER};
                border-left: 4px solid {border_color};
                border-radius: {tokens.RADIUS}px;
            }}
        """))

        # Auto dismiss after 6 seconds unless kind == "error"
        if kind != "error":
            self._dismiss_timer = QTimer(self)
            self._dismiss_timer.setSingleShot(True)
            self._dismiss_timer.timeout.connect(self._dismiss)
            self._dismiss_timer.start(6000)

    @Slot()
    def _dismiss(self) -> None:
        if self._is_dismissed:
            return
        self._is_dismissed = True
        if self._dismiss_timer is not None:
            self._dismiss_timer.stop()
            self._dismiss_timer = None
        try:
            self.dismissed.emit(self)
        except RuntimeError:
            pass

    def deleteLater(self) -> None:
        """Clean up timer before destruction."""
        if self._dismiss_timer is not None:
            self._dismiss_timer.stop()
            self._dismiss_timer = None
        super().deleteLater()


class ToastOverlay(QWidget):
    """Container anchored bottom-right showing at most 3 active toasts."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("studioToastOverlay")
        self.setAccessibleName("Notifications overlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignBottom | Qt.AlignRight)

        self._toasts: List[ToastCard] = []
        if parent:
            parent.installEventFilter(self)
        self.hide()
        self._reposition()

    def eventFilter(self, watched: Optional[QObject], event: Optional[QEvent]) -> bool:
        if event is not None and watched == self.parentWidget() and event.type() in (QEvent.Resize, QEvent.Show):
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
        self.show()
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

    @Slot(object)
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
        if not self._toasts:
            self.hide()
            return
        self.show()
        self._layout.activate()
        pw = parent.width()
        ph = parent.height()
        w = 340
        h = max(60, self._layout.sizeHint().height(), len(self._toasts) * 90)
        self.setGeometry(pw - w - 20, ph - h - 30, w, h)

    def resizeEvent(self, event: Optional[QResizeEvent]) -> None:
        super().resizeEvent(event)
        self._reposition()

    def deleteLater(self) -> None:
        """Clean up parent event filter and child toasts on destruction."""
        parent = self.parentWidget()
        if parent:
            try:
                parent.removeEventFilter(self)
            except (RuntimeError, TypeError):
                pass
        for toast in list(self._toasts):
            try:
                toast.deleteLater()
            except (RuntimeError, TypeError):
                pass
        self._toasts.clear()
        super().deleteLater()
