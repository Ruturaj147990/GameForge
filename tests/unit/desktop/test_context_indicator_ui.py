"""Comprehensive PySide6 UI Unit Tests for Context-Usage Indicator (DEF-303).

Validates:
1. ContextUsageIndicator widget:
   - Visual progress bar, tokens label, and Exact/Estimated badge
   - Consuming authoritative ContextUsageReport and dict representations
   - Progress bar threshold color grading (<70% green, 70-85% amber, >85% red)
   - Exact vs Estimated badge visual styling
2. Expandable Breakdown Dialog & Tooltip:
   - Comprehensive tooltip detailing all 7 context categories
   - ContextBreakdownDialog popup modal displaying all 7 token breakdown rows
3. ChatPanel Integration:
   - Embedding of ContextUsageIndicator in ChatPanel toolbar
   - Dynamic telemetry updates via set_context_usage() and chat events
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from src.gameforge_ide.backend.models.context_usage import ContextBreakdown, ContextUsageReport
from src.gameforge_ide.desktop.panels.chat_panel import ChatPanel
from src.gameforge_ide.desktop.styles import tokens
from src.gameforge_ide.desktop.widgets.context_indicator import (
    ContextBreakdownDialog,
    ContextUsageIndicator,
    _format_token_count,
)


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "test_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ==============================================================================
# 1. Format Helper Tests
# ==============================================================================

def test_format_token_count_helper():
    """Verify human-readable token number formatting."""
    assert _format_token_count(500) == "500"
    assert _format_token_count(4200) == "4,200"
    assert _format_token_count(32768) == "32.8k"
    assert _format_token_count(128000) == "128k"


# ==============================================================================
# 2. ContextUsageIndicator Standalone Widget Tests
# ==============================================================================

def test_context_indicator_initial_state(qapp: QApplication):
    """Verify initial creation and layout of ContextUsageIndicator."""
    indicator = ContextUsageIndicator()
    try:
        assert indicator.objectName() == "contextUsageIndicator"
        assert indicator.accessibleName() == "Context Usage Indicator"
        assert indicator._progress is not None
        assert indicator._progress.value() == 0
        assert indicator._badge.text() == "EST"
        assert indicator.get_report() is None
    finally:
        indicator.deleteLater()


def test_context_indicator_consume_exact_report(qapp: QApplication):
    """Verify indicator consumes an exact ContextUsageReport."""
    indicator = ContextUsageIndicator()
    try:
        breakdown = ContextBreakdown(
            system_prompt=1200,
            conversation=2500,
            memory=400,
            retrieved_docs=1000,
            tool_definitions=1500,
            other_overhead=150,
            reserved_output=2048,
        )
        report = ContextUsageReport.create(
            model_id="gameforge-qwen3.5-9b",
            nominal_capacity=32768,
            breakdown=breakdown,
            reserved_output=2048,
            is_exact=True,
            session_id="test_sess_1",
        )

        indicator.update_report(report)

        assert indicator.get_report() == report
        assert indicator._badge.text() == "EXACT"
        assert indicator._progress.value() == int(round(report.utilization_pct))
        assert "6,750" in indicator._lbl_tokens.text()
        assert "32.8k" in indicator._lbl_tokens.text()

        # Tooltip must contain all 7 categories
        tip = indicator.toolTip()
        assert "gameforge-qwen3.5-9b" in tip
        assert "Exact provider measurement" in tip
        assert "1. System / developer prompt" in tip
        assert "2. Conversation history" in tip
        assert "3. Long-term memory" in tip
        assert "4. Retrieved files/documents" in tip
        assert "5. Tool definitions" in tip
        assert "6. Other prompt overhead" in tip
        assert "7. Reserved completion capacity" in tip
    finally:
        indicator.deleteLater()


def test_context_indicator_consume_estimated_report_and_dict(qapp: QApplication):
    """Verify indicator consumes an estimated report passed as dict."""
    indicator = ContextUsageIndicator()
    try:
        dict_payload: Dict[str, Any] = {
            "model_id": "gameforge-qwen3.5-4b",
            "nominal_capacity": 16384,
            "effective_budget": 14336,
            "used_tokens": 12000,
            "remaining_tokens": 2336,
            "utilization_pct": 83.7,
            "is_estimated": True,
            "estimation_method": "char_ratio",
            "breakdown": {
                "system_prompt": 1000,
                "conversation": 8000,
                "memory": 500,
                "retrieved_docs": 1000,
                "tool_definitions": 1200,
                "other_overhead": 300,
                "reserved_output": 2048,
            },
        }

        indicator.update_report(dict_payload)

        assert indicator.get_report() is not None
        assert indicator._badge.text() == "EST"
        assert indicator._progress.value() == 84
        assert "12.0k" in indicator._lbl_tokens.text()
        assert "16.4k" in indicator._lbl_tokens.text()

        tip = indicator.toolTip()
        assert "gameforge-qwen3.5-4b" in tip
        assert "Estimated (char_ratio)" in tip
    finally:
        indicator.deleteLater()


def test_context_indicator_color_grading_thresholds(qapp: QApplication):
    """Verify progress bar color changes across <70%, 70-85%, and >85%."""
    indicator = ContextUsageIndicator()
    try:
        # Case 1: Low usage (< 70%) -> Success color
        b1 = ContextBreakdown(system_prompt=1000, conversation=2000)
        r1 = ContextUsageReport.create("m", 32768, b1)
        indicator.update_report(r1)
        assert tokens.ACCENT_SUCCESS in indicator._progress.styleSheet()

        # Case 2: Medium usage (75%) -> Warning color
        b2 = ContextBreakdown(system_prompt=10000, conversation=13000)
        r2 = ContextUsageReport.create("m", 32768, b2)
        indicator.update_report(r2)
        assert tokens.ACCENT_WARNING in indicator._progress.styleSheet()

        # Case 3: High usage (92%) -> Error color
        b3 = ContextBreakdown(system_prompt=10000, conversation=18500)
        r3 = ContextUsageReport.create("m", 32768, b3)
        indicator.update_report(r3)
        assert tokens.ACCENT_ERROR in indicator._progress.styleSheet()
    finally:
        indicator.deleteLater()


# ==============================================================================
# 3. ContextBreakdownDialog Popup Modal Tests
# ==============================================================================

def test_context_breakdown_dialog_elements(qapp: QApplication):
    """Verify ContextBreakdownDialog renders all 7 categories and budget numbers."""
    breakdown = ContextBreakdown(
        system_prompt=1500,
        conversation=4500,
        memory=800,
        retrieved_docs=3200,
        tool_definitions=2100,
        other_overhead=400,
        reserved_output=2048,
    )
    report = ContextUsageReport.create(
        model_id="gameforge-27b-sft",
        nominal_capacity=65536,
        breakdown=breakdown,
        reserved_output=2048,
        is_exact=True,
    )

    dialog = ContextBreakdownDialog(report)
    try:
        assert dialog.objectName() == "contextBreakdownDialog"
        assert dialog.windowTitle() == "Context Usage Breakdown"

        # Check all categories appear in child labels
        text_blobs = [lbl.text() for lbl in dialog.findChildren(QLabel)]
        all_text = " ".join(text_blobs)

        assert "gameforge-27b-sft" in all_text
        assert "EXACT" in all_text
        assert "1. System / developer prompt" in all_text
        assert "2. Conversation history" in all_text
        assert "3. Long-term memory" in all_text
        assert "4. Retrieved files/documents" in all_text
        assert "5. Tool definitions" in all_text
        assert "6. Other prompt overhead" in all_text
        assert "7. Reserved completion capacity" in all_text
        assert "Total Consumed (Prompt)" in all_text
        assert "Remaining Usable Budget" in all_text
    finally:
        dialog.close()
        dialog.deleteLater()


# ==============================================================================
# 4. ChatPanel Integration Tests
# ==============================================================================

def test_chat_panel_context_indicator_embedded_and_updated(qapp: QApplication, temp_workspace: Path):
    """Verify ChatPanel embeds ContextUsageIndicator and updates dynamically."""
    chat = ChatPanel(workspace_root=temp_workspace)
    try:
        assert hasattr(chat, "context_indicator")
        assert chat.context_indicator is not None
        assert chat.context_indicator.objectName() == "chatContextIndicator"

        # Updating via set_context_usage()
        b = ContextBreakdown(system_prompt=1200, conversation=3000)
        r = ContextUsageReport.create("chat-model", 32768, b, is_exact=True)
        chat.set_context_usage(r)

        assert chat.context_indicator.get_report() == r
        assert chat.context_indicator._badge.text() == "EXACT"

        # Adding a bubble refreshes context usage estimate
        chat._add_bubble("user", "Hello GameForge! Can you explain the project structure?")
        assert chat.context_indicator.get_report() is not None
    finally:
        chat.deleteLater()
