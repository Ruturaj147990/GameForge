"""Tests for Agent 2 Runtime Hardening and Context Budgeting."""

import pytest
from pathlib import Path

from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.agent.tool_call_parser import parse_text_for_tool_calls


def test_runtime_extract_screenshot_flat_command():
    """Verify that runtime._extract_tool_call handles the flat command dialect from screenshot."""
    runtime = AgentRuntime(Path("."))
    payload = (
        "I will inspect the file now:\n\n"
        '{\n  "command": "read_file",\n  "path": "E:\\\\GameForge\\\\projects\\\\CounterStrike\\\\Source\\\\CounterStrike\\\\GFGameImpl.cpp"\n}\n\n'
        "Reading file..."
    )
    extracted = runtime._extract_tool_call(payload)
    assert extracted is not None
    assert extracted["name"] == "read_file"
    assert extracted["arguments"]["path"] == "E:\\GameForge\\projects\\CounterStrike\\Source\\CounterStrike\\GFGameImpl.cpp"


def test_runtime_clean_narrative_preserves_surrounding_text():
    """Verify that _clean_narrative_text keeps prose before and after and removes tool payload."""
    payload = (
        "Analyzing error:\n"
        '{\n  "command": "read_file",\n  "path": "GFGameImpl.cpp"\n}\n'
        "Awaiting results."
    )
    cleaned = AgentRuntime._clean_narrative_text(payload)
    assert "Analyzing error:" in cleaned
    assert "Awaiting results." in cleaned
    assert "read_file" not in cleaned
    assert '{"command"' not in cleaned


def test_fit_history_to_context_budget_propagation():
    """Verify that fit_history_to_context returns effective output_tokens and context_limit_tokens."""
    system_prompt = "You are GameForge agent."
    messages = [
        {"role": "user", "content": "Help me fix my game."},
        {"role": "assistant", "content": "Sure, let's fix it."},
        {"role": "user", "content": "Now compile it."},
    ]

    selected, budget = AgentRuntime.fit_history_to_context(
        system_prompt=system_prompt,
        messages=messages,
        max_context=4096,
        output_tokens=1024,
        safety_tokens=128,
    )

    assert "output_tokens" in budget
    assert budget["output_tokens"] == 1024
    assert "context_limit_tokens" in budget
    assert budget["context_limit_tokens"] == 4096
    assert "safety_tokens" in budget
    assert budget["safety_tokens"] == 128
    assert "input_budget_tokens" in budget
    assert "estimated_input_tokens" in budget
    assert budget["estimated_input_tokens"] <= budget["input_budget_tokens"]


def test_fit_history_to_context_tight_boundary_adaptation():
    """Verify that fit_history_to_context adapts output reservation for small 2K contexts."""
    # Long system prompt ~1400 tokens
    long_system = "Instructions:\n" + ("Do not fail. " * 300)
    messages = [{"role": "user", "content": "Hello"}]

    selected, budget = AgentRuntime.fit_history_to_context(
        system_prompt=long_system,
        messages=messages,
        max_context=2048,
        output_tokens=1024,
        safety_tokens=128,
    )

    assert budget["output_tokens"] < 1024
    assert budget["output_tokens"] >= 256
    assert budget["context_limit_tokens"] == 2048


def test_is_tool_call_start_detects_command_dialect():
    """Verify that _is_tool_call_start recognizes the screenshot's command prefix."""
    text1 = '{"command": "read_file", "path": "foo.cpp"}'
    assert AgentRuntime._is_tool_call_start(text1) is True

    text2 = '{\n  "command": "read_file",\n  "path": "bar.h"\n}'
    assert AgentRuntime._is_tool_call_start(text2) is True

    text3 = "Just a normal narrative sentence without tool calls."
    assert AgentRuntime._is_tool_call_start(text3) is False
