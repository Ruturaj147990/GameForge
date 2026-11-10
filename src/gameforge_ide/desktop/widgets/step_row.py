"""StepRow delegate for Build view timeline (spec §4.4, WI-4.7)."""
from __future__ import annotations

import math
import time
from typing import Optional, Tuple

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ..styles import tokens
from ..styles.dark_theme import theme_color
from ...forge.model import StepRecord

STEP_ROLE = Qt.UserRole + 1


def format_step_duration(started_at: Optional[float], finished_at: Optional[float]) -> str:
    """Format duration in seconds or mm:ss."""
    if started_at is None:
        return ""
    try:
        start_val = float(started_at)
        end_val = time.time() if finished_at is None else float(finished_at)
    except (TypeError, ValueError):
        return ""
    if not (math.isfinite(start_val) and math.isfinite(end_val)):
        return ""
    dur = max(0.0, end_val - start_val)
    if dur < 60:
        return f"{dur:.1f} s"
    mins = int(dur // 60)
    secs = int(dur % 60)
    return f"{mins:02d}:{secs:02d}"


class StepRowDelegate(QStyledItemDelegate):
    """Paints timeline step items with status icon, duration, and checkpoint badge."""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(max(120, option.rect.width()), 36)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        step: Optional[StepRecord] = index.data(STEP_ROLE)
        if not step or not hasattr(step, "status"):
            super().paint(painter, option, index)
            return

        r = option.rect.adjusted(4, 2, -4, -2)
        if r.width() <= 4 or r.height() <= 4:
            return

        painter.save()
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)

            is_hover = bool(option.state & QStyle.State_MouseOver)
            is_selected = bool(option.state & QStyle.State_Selected)
            has_focus = bool(option.state & QStyle.State_HasFocus)

            # Background & WCAG focus outline
            if is_hover:
                bg_col = QColor(theme_color(tokens.BG_HOVER))
            elif is_selected:
                bg_col = QColor(theme_color(tokens.BG_ACTIVE))
            else:
                bg_col = QColor(theme_color(tokens.BG_SURFACE))

            if has_focus:
                border_col = QColor(theme_color(tokens.BORDER_FOCUS))
                border_width = 1.5
            elif is_selected:
                border_col = QColor(theme_color(tokens.ACCENT_PRIMARY))
                border_width = 1.0
            else:
                border_col = QColor(theme_color(tokens.BORDER))
                border_width = 1.0

            painter.setBrush(QBrush(bg_col))
            painter.setPen(QPen(border_col, border_width))
            painter.drawRoundedRect(r, tokens.RADIUS, tokens.RADIUS)

            # Status icon
            raw_status = getattr(step, "status", "")
            st = (raw_status.value if hasattr(raw_status, "value") else str(raw_status or "")).strip().upper()
            icon_symbol, icon_color = self._get_status_icon(st)
            painter.setPen(QColor(theme_color(icon_color)))
            font = painter.font()
            font.setPointSize(tokens.FONT_BODY)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRect(r.x() + 8, r.y(), 20, r.height()), Qt.AlignCenter, icon_symbol)

            # Duration & Checkpoint Badge
            title_left = r.x() + 32
            right_x = r.right() - 8
            dur_str = format_step_duration(getattr(step, "started_at", None), getattr(step, "finished_at", None))

            font.setPointSize(tokens.FONT_BODY_SM)
            painter.setFont(font)

            if getattr(step, "checkpoint", None) and (right_x - title_left) > 90:
                ckpt_w = 48
                ckpt_rect = QRect(right_x - ckpt_w, r.y() + (r.height() - 18) // 2, ckpt_w, 18)
                painter.setBrush(QBrush(QColor(theme_color(tokens.BG_PANEL))))
                painter.setPen(QPen(QColor(theme_color(tokens.ACCENT_HOVER)), 0.75))
                painter.drawRoundedRect(ckpt_rect, 3, 3)
                painter.setPen(QColor(theme_color(tokens.ACCENT_HOVER)))
                painter.drawText(ckpt_rect, Qt.AlignCenter, "⎘ ckpt")
                right_x -= (ckpt_w + 6)

            if dur_str and (right_x - title_left) > 60:
                dur_w = max(60, painter.fontMetrics().horizontalAdvance(dur_str) + 8)
                painter.setPen(QColor(theme_color(tokens.TEXT_MUTED)))
                painter.drawText(
                    QRect(right_x - dur_w, r.y(), dur_w, r.height()),
                    Qt.AlignRight | Qt.AlignVCenter,
                    dur_str,
                )
                right_x -= (dur_w + 8)

            # Step ID / Title (elided cleanly into remaining space)
            font.setPointSize(tokens.FONT_BODY)
            font.setBold(False)
            painter.setFont(font)
            text_color = (
                tokens.TEXT_PRIMARY
                if st in ("DONE", "RUNNING", "FAILED", "FAIL", "CANCELLED", "CANCELED", "INTERRUPTED")
                else tokens.TEXT_MUTED
            )
            painter.setPen(QColor(theme_color(text_color)))
            raw_id = str(getattr(step, "step_id", "") or "step")
            title_text = raw_id.replace("_", " ").capitalize()
            avail_w = max(24, right_x - title_left - 8)
            elided_title = painter.fontMetrics().elidedText(title_text, Qt.ElideRight, avail_w)
            painter.drawText(QRect(title_left, r.y(), avail_w, r.height()), Qt.AlignLeft | Qt.AlignVCenter, elided_title)
        finally:
            painter.restore()

    def _get_status_icon(self, status: str) -> Tuple[str, str]:
        st = (status.value if hasattr(status, "value") else str(status or "")).strip().upper()
        if st == "DONE":
            return "✓", tokens.ACCENT_SUCCESS
        if st == "RUNNING":
            return "◉", tokens.ACCENT_WARNING
        if st == "PENDING":
            return "○", tokens.TEXT_MUTED
        if st in ("FAILED", "FAIL"):
            return "✕", tokens.ACCENT_ERROR
        if st in ("CANCELLED", "CANCELED", "INTERRUPTED"):
            return "⏹", tokens.ACCENT_WARNING
        if st == "WAITING_APPROVAL":
            return "⏸", tokens.ACCENT_WARNING
        if st == "BLOCKED":
            return "⊘", tokens.TEXT_MUTED
        if st == "SKIPPED":
            return "↷", tokens.TEXT_MUTED
        return "○", tokens.TEXT_MUTED
