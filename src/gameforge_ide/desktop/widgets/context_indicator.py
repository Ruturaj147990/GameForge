"""Context-Usage Indicator and Detailed Breakdown Widget for GameForge IDE (DEF-303).

Provides compact real-time visual context accounting matching tokens.py:
- Active model identifier
- Nominal context capacity and effective prompt budget
- Tokens consumed, remaining tokens, and percentage used
- Visual progress bar with dynamic color grading (<70% green, 70-85% amber, >85% red)
- Exact vs. Estimated badge
- Rich hover tooltip and expandable popup detailing all 7 breakdown categories:
  1. System/developer prompt
  2. Conversation history
  3. Long-term memory
  4. Retrieved files/documents
  5. Tool definitions
  6. Other prompt overhead
  7. Reserved completion capacity
"""

from __future__ import annotations

import html
from typing import Any, Dict, Optional, Union

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ...backend.models.context_usage import ContextBreakdown, ContextUsageReport
from ..styles import tokens
from ..styles.dark_theme import theme_color, theme_stylesheet


def _format_token_count(tokens_count: int) -> str:
    """Format token count into compact human readable string (e.g. 4.2k or 32,768)."""
    if tokens_count >= 100_000:
        return f"{tokens_count / 1000:.0f}k"
    elif tokens_count >= 10_000:
        return f"{tokens_count / 1000:.1f}k"
    return f"{tokens_count:,}"


class ContextBreakdownDialog(QDialog):
    """Detailed popup modal dialog displaying all token breakdown categories."""

    def __init__(self, report: ContextUsageReport, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Context Usage Breakdown")
        self.setObjectName("contextBreakdownDialog")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)

        self._report = report
        self._init_ui()

    def _init_ui(self) -> None:
        bg = theme_color(tokens.BG_PANEL)
        border_col = theme_color(tokens.BORDER_FOCUS)
        text_pri = theme_color(tokens.TEXT_PRIMARY)
        text_sec = theme_color(tokens.TEXT_SECONDARY)

        self.setStyleSheet(f"""
            QDialog#contextBreakdownDialog {{
                background-color: {bg};
                border: 1px solid {border_col};
                border-radius: {tokens.RADIUS_LG}px;
                padding: 12px;
            }}
            QLabel {{
                background: transparent;
                color: {text_pri};
                font-size: {tokens.FONT_BODY_SM}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Header: Model & Status
        hdr = QHBoxLayout()
        title_lbl = QLabel(f"<b>Model:</b> <code style='color:{tokens.ACCENT_PRIMARY};'>{html.escape(self._report.model_id)}</code>")
        title_lbl.setTextFormat(Qt.RichText)
        hdr.addWidget(title_lbl)
        hdr.addStretch()

        badge_text = "EXACT" if not self._report.is_estimated else f"EST ({self._report.estimation_method})"
        badge_bg = tokens.ACCENT_SUCCESS if not self._report.is_estimated else tokens.ACCENT_WARNING
        badge_lbl = QLabel(f"<span style='background-color:{badge_bg}; color:#000; border-radius:3px; padding:2px 6px; font-weight:bold; font-size:10px;'>{badge_text}</span>")
        badge_lbl.setTextFormat(Qt.RichText)
        hdr.addWidget(badge_lbl)
        layout.addLayout(hdr)

        # Overview Grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)

        b = self._report.breakdown
        items = [
            ("1. System / developer prompt", b.system_prompt),
            ("2. Conversation history", b.conversation),
            ("3. Long-term memory", b.memory),
            ("4. Retrieved files/documents", b.retrieved_docs),
            ("5. Tool definitions", b.tool_definitions),
            ("6. Other prompt overhead", b.other_overhead),
            ("7. Reserved completion capacity", b.reserved_output),
        ]

        row = 0
        for name, val in items:
            pct = (val / self._report.nominal_capacity * 100.0) if self._report.nominal_capacity > 0 else 0.0
            lbl_name = QLabel(name)
            lbl_name.setStyleSheet(f"color: {text_sec};")
            lbl_val = QLabel(f"<b>{val:,}</b> tokens ({pct:.1f}%)")
            lbl_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(lbl_name, row, 0)
            grid.addWidget(lbl_val, row, 1)
            row += 1

        # Divider
        div = QFrame(self)
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"background-color: {tokens.BORDER}; height: 1px;")
        grid.addWidget(div, row, 0, 1, 2)
        row += 1

        # Totals
        lbl_tot_name = QLabel("<b>Total Consumed (Prompt)</b>")
        lbl_tot_val = QLabel(f"<b>{self._report.used_tokens:,} / {self._report.nominal_capacity:,}</b> ({self._report.utilization_pct:.1f}%)")
        lbl_tot_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid.addWidget(lbl_tot_name, row, 0)
        grid.addWidget(lbl_tot_val, row, 1)
        row += 1

        lbl_rem_name = QLabel("Remaining Usable Budget")
        lbl_rem_val = QLabel(f"<b>{self._report.remaining_tokens:,}</b> tokens")
        lbl_rem_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid.addWidget(lbl_rem_name, row, 0)
        grid.addWidget(lbl_rem_val, row, 1)

        layout.addLayout(grid)

        # Close hint
        close_btn = QPushButton("Close", self)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {tokens.BG_SURFACE};
                border: 1px solid {tokens.BORDER};
                border-radius: {tokens.RADIUS}px;
                padding: 4px 10px;
                color: {tokens.TEXT_SECONDARY};
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {tokens.BG_HOVER};
                color: {tokens.TEXT_PRIMARY};
            }}
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, 0, Qt.AlignRight)


class ContextUsageIndicator(QFrame):
    """Compact context-usage indicator widget embedded in ChatPanel."""

    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("contextUsageIndicator")
        self.setAccessibleName("Context Usage Indicator")
        self.setCursor(Qt.PointingHandCursor)

        self._report: Optional[ContextUsageReport] = None
        self._init_ui()

    def _init_ui(self) -> None:
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)
        layout.setSizeConstraint(QHBoxLayout.SetFixedSize)

        # Icon / Label
        self._lbl_icon = QLabel("📊", self)
        self._lbl_icon.setStyleSheet("font-size: 11px;")
        self._lbl_icon.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        layout.addWidget(self._lbl_icon)

        # Numerical label (e.g. "4.2k / 32k (13%)")
        self._lbl_tokens = QLabel("0 / 32k (0%)", self)
        self._lbl_tokens.setObjectName("lblContextTokens")
        self._lbl_tokens.setStyleSheet(f"font-size: {tokens.FONT_BODY_SM}px; font-weight: 600; color: {tokens.TEXT_PRIMARY};")
        self._lbl_tokens.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        layout.addWidget(self._lbl_tokens)

        # Visual progress bar
        self._progress = QProgressBar(self)
        self._progress.setObjectName("contextProgressBar")
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedWidth(54)
        self._progress.setFixedHeight(6)
        layout.addWidget(self._progress)

        # Exact / Estimated badge
        self._badge = QLabel("EST", self)
        self._badge.setObjectName("lblContextBadge")
        self._badge.setStyleSheet(f"""
            QLabel#lblContextBadge {{
                background-color: {tokens.BG_SURFACE};
                border: 1px solid {tokens.BORDER};
                border-radius: 3px;
                padding: 1px 4px;
                font-size: 9px;
                font-weight: 700;
                color: {tokens.TEXT_MUTED};
            }}
        """)
        layout.addWidget(self._badge)

        self.update_theme()
        self._update_tooltip()

    def update_theme(self) -> None:
        """Apply active theme tokens to indicator frame and progress bar."""
        bg = theme_color(tokens.BG_SURFACE)
        border_col = theme_color(tokens.BORDER)
        text_pri = theme_color(tokens.TEXT_PRIMARY)

        util_pct = self._report.utilization_pct if self._report else 0.0
        bar_color = tokens.ACCENT_SUCCESS if util_pct < 70.0 else (tokens.ACCENT_WARNING if util_pct <= 85.0 else tokens.ACCENT_ERROR)

        self.setStyleSheet(f"""
            QFrame#contextUsageIndicator {{
                background-color: {bg};
                border: 1px solid {border_col};
                border-radius: {tokens.RADIUS}px;
            }}
            QFrame#contextUsageIndicator:hover {{
                border-color: {tokens.BORDER_FOCUS};
                background-color: {tokens.BG_HOVER};
            }}
        """)

        self._progress.setStyleSheet(f"""
            QProgressBar#contextProgressBar {{
                background-color: {tokens.BG_ROOT};
                border: 1px solid {tokens.BORDER};
                border-radius: 3px;
                height: 6px;
            }}
            QProgressBar#contextProgressBar::chunk {{
                background-color: {bar_color};
                border-radius: 2px;
            }}
        """)

        self._lbl_tokens.setStyleSheet(f"font-size: {tokens.FONT_BODY_SM}px; font-weight: 600; color: {text_pri};")

    def update_report(self, report: Union[ContextUsageReport, Dict[str, Any]]) -> None:
        """Update indicator with newly calculated ContextUsageReport or dict."""
        if isinstance(report, dict):
            breakdown_dict = report.get("breakdown", {})
            breakdown = ContextBreakdown(
                system_prompt=breakdown_dict.get("system_prompt", 0),
                conversation=breakdown_dict.get("conversation", 0),
                memory=breakdown_dict.get("memory", 0),
                retrieved_docs=breakdown_dict.get("retrieved_docs", 0),
                tool_definitions=breakdown_dict.get("tool_definitions", 0),
                other_overhead=breakdown_dict.get("other_overhead", 0),
                reserved_output=breakdown_dict.get("reserved_output", 2048),
            )
            self._report = ContextUsageReport(
                model_id=report.get("model_id", "default-model"),
                nominal_capacity=report.get("nominal_capacity", 32768),
                effective_budget=report.get("effective_budget", 30720),
                used_tokens=report.get("used_tokens", 0),
                remaining_tokens=report.get("remaining_tokens", 30720),
                utilization_pct=float(report.get("utilization_pct", 0.0)),
                is_estimated=bool(report.get("is_estimated", True)),
                estimation_method=str(report.get("estimation_method", "char_ratio")),
                breakdown=breakdown,
            )
        else:
            self._report = report

        # Update text label
        used_fmt = _format_token_count(self._report.used_tokens)
        nom_fmt = _format_token_count(self._report.nominal_capacity)
        pct = self._report.utilization_pct
        if pct > 100.0:
            self._lbl_tokens.setText(f"{used_fmt} / {nom_fmt} ({pct:.0f}% - Overflow)")
        else:
            self._lbl_tokens.setText(f"{used_fmt} / {nom_fmt} ({pct:.0f}%)")

        # Update progress bar
        val = int(min(100, max(0, round(pct))))
        self._progress.setValue(val)

        # Update badge
        if not self._report.is_estimated:
            self._badge.setText("EXACT")
            self._badge.setStyleSheet(f"""
                QLabel#lblContextBadge {{
                    background-color: {tokens.ACCENT_SUCCESS};
                    color: {tokens.BG_ROOT};
                    border: none;
                    border-radius: 3px;
                    padding: 1px 4px;
                    font-size: 9px;
                    font-weight: 800;
                }}
            """)
        else:
            self._badge.setText("EST")
            self._badge.setStyleSheet(f"""
                QLabel#lblContextBadge {{
                    background-color: {tokens.BG_SURFACE};
                    border: 1px solid {tokens.ACCENT_WARNING};
                    border-radius: 3px;
                    padding: 1px 4px;
                    font-size: 9px;
                    font-weight: 700;
                    color: {tokens.ACCENT_WARNING};
                }}
            """)

        self.update_theme()
        self._update_tooltip()

    def get_report(self) -> Optional[ContextUsageReport]:
        """Return the current context-usage report."""
        return self._report

    def _update_tooltip(self) -> None:
        """Construct a high-density, formatted HTML tooltip breakdown."""
        if not self._report:
            self.setToolTip("Context Usage: No active data. Click to inspect.")
            return

        b = self._report.breakdown
        badge_text = "Exact provider measurement" if not self._report.is_estimated else f"Estimated ({self._report.estimation_method})"
        html_tip = f"""
        <div style='font-family: Segoe UI, sans-serif; font-size: 11px; color: {tokens.TEXT_PRIMARY}; padding: 4px;'>
          <b style='color:{tokens.ACCENT_HOVER}; font-size:12px;'>Context Usage: {html.escape(self._report.model_id)}</b><br>
          <span>Budget: <b>{self._report.used_tokens:,}</b> / <b>{self._report.nominal_capacity:,}</b> tokens ({self._report.utilization_pct:.1f}%)</span><br>
          <span style='color:{tokens.TEXT_SECONDARY};'>Remaining prompt budget: {self._report.remaining_tokens:,} tokens</span><br>
          <span style='color:{tokens.TEXT_MUTED}; font-size:10px;'>Accounting: {badge_text}</span>
          <hr style='border:0; border-top:1px solid {tokens.BORDER}; margin:6px 0;'>
          <table style='width:100%; border-collapse:collapse; font-size:11px;'>
            <tr><td style='color:{tokens.TEXT_SECONDARY};'>1. System / developer prompt:</td><td align='right'><b>{b.system_prompt:,}</b></td></tr>
            <tr><td style='color:{tokens.TEXT_SECONDARY};'>2. Conversation history:</td><td align='right'><b>{b.conversation:,}</b></td></tr>
            <tr><td style='color:{tokens.TEXT_SECONDARY};'>3. Long-term memory:</td><td align='right'><b>{b.memory:,}</b></td></tr>
            <tr><td style='color:{tokens.TEXT_SECONDARY};'>4. Retrieved files/documents:</td><td align='right'><b>{b.retrieved_docs:,}</b></td></tr>
            <tr><td style='color:{tokens.TEXT_SECONDARY};'>5. Tool definitions:</td><td align='right'><b>{b.tool_definitions:,}</b></td></tr>
            <tr><td style='color:{tokens.TEXT_SECONDARY};'>6. Other prompt overhead:</td><td align='right'><b>{b.other_overhead:,}</b></td></tr>
            <tr><td style='color:{tokens.TEXT_SECONDARY};'>7. Reserved completion capacity:</td><td align='right'><b>{b.reserved_output:,}</b></td></tr>
          </table>
          <hr style='border:0; border-top:1px solid {tokens.BORDER}; margin:6px 0;'>
          <span style='color:{tokens.ACCENT_HOVER}; font-size:10px;'>💡 Click indicator to open persistent breakdown popup</span>
        </div>
        """
        self.setToolTip(html_tip)

    def mousePressEvent(self, event) -> None:
        """Show the detailed popup breakdown dialog on mouse click."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            if self._report:
                if hasattr(self, "_active_dialog") and self._active_dialog and self._active_dialog.isVisible():
                    self._active_dialog.close()
                    self._active_dialog = None
                    return
                dialog = ContextBreakdownDialog(self._report, self)
                self._active_dialog = dialog
                # Position near indicator
                pos = self.mapToGlobal(QPoint(0, self.height() + 4))
                screen = self.screen() or (self.window().screen() if self.window() else None)
                if screen:
                    s_geom = screen.availableGeometry()
                    d_w = dialog.sizeHint().width()
                    d_h = dialog.sizeHint().height()
                    if pos.x() + d_w > s_geom.right():
                        pos.setX(max(s_geom.left(), s_geom.right() - d_w - 10))
                    if pos.y() + d_h > s_geom.bottom():
                        pos.setY(max(s_geom.top(), pos.y() - self.height() - d_h - 8))
                dialog.move(pos)
                dialog.show()
                dialog.raise_()
        super().mousePressEvent(event)
