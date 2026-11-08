"""Tests for the canonical tool call parser, normalizer, and streaming guard."""

import random
import pytest

from src.gameforge_ide.backend.agent.tool_call_parser import (
    ParsedToolCall,
    ParserResult,
    StreamingToolGuard,
    find_balanced_json_objects,
    normalize_flat_command,
    normalize_tool_dict,
    parse_text_for_tool_calls,
    DEFAULT_KNOWN_TOOLS,
    DEFAULT_ALIASES,
)


def test_screenshot_flat_command_dialect():
    """Verify that the exact flat command format from the user screenshot is recognized."""
    data = {
        "command": "read_file",
        "path": "E:\\GameForge\\projects\\CounterStrike\\Source\\CounterStrike\\GFGameImpl.cpp",
    }
    res = normalize_flat_command(data, DEFAULT_KNOWN_TOOLS, DEFAULT_ALIASES)
    assert res is not None
    name, args = res
    assert name == "read_file"
    assert args == {
        "path": "E:\\GameForge\\projects\\CounterStrike\\Source\\CounterStrike\\GFGameImpl.cpp"
    }


def test_screenshot_payload_in_prose_cleaned():
    """Verify that surrounding prose is preserved and only the tool call is extracted and excised."""
    payload = (
        "I will now inspect the source file to diagnose the color issue.\n\n"
        '{\n  "command": "read_file",\n  "path": "E:\\\\GameForge\\\\projects\\\\CounterStrike\\\\Source\\\\CounterStrike\\\\GFGameImpl.cpp"\n}\n\n'
        "Please wait while I read this file."
    )
    res = parse_text_for_tool_calls(payload)
    assert len(res.calls) == 1
    call = res.calls[0]
    assert call.name == "read_file"
    assert call.arguments["path"] == "E:\\GameForge\\projects\\CounterStrike\\Source\\CounterStrike\\GFGameImpl.cpp"
    assert "I will now inspect the source file" in res.cleaned_text
    assert "Please wait while I read this file." in res.cleaned_text
    assert '"command"' not in res.cleaned_text
    assert "read_file" not in res.cleaned_text


def test_streaming_guard_single_char_chunking():
    """Verify that single-character streamed chunks prevent tool JSON leakage and extract call."""
    payload = (
        "Inspecting implementation:\n"
        '{\n  "command": "read_file",\n  "path": "Source/CounterStrike/GFGameImpl.cpp"\n}\n'
        "Done reading."
    )
    guard = StreamingToolGuard()
    narrative_chunks = []
    calls = []

    for char in payload:
        safe_delta, new_calls = guard.feed(char)
        if safe_delta:
            narrative_chunks.append(safe_delta)
        calls.extend(new_calls)

    tail, final_calls = guard.finish()
    if tail:
        narrative_chunks.append(tail)
    calls.extend(final_calls)

    full_narrative = "".join(narrative_chunks)
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert calls[0].arguments == {"path": "Source/CounterStrike/GFGameImpl.cpp"}
    assert "Inspecting implementation:" in full_narrative
    assert "Done reading." in full_narrative
    assert '{"command"' not in full_narrative
    assert '"read_file"' not in full_narrative


def test_streaming_guard_random_chunk_fuzzing():
    """Verify that 100 randomized chunk splits yield identical clean narrative and tool extraction."""
    payload = (
        "Checking directory structure.\n"
        '{\n  "command": "list_dir",\n  "subpath": "Source/CounterStrike"\n}\n'
        "Directory listed."
    )
    rng = random.Random(42)

    for _ in range(100):
        # Generate random chunk slice boundaries
        indices = sorted(rng.sample(range(1, len(payload)), k=min(10, len(payload) - 1)))
        boundaries = [0] + indices + [len(payload)]
        chunks = [payload[boundaries[i]:boundaries[i+1]] for i in range(len(boundaries) - 1)]

        guard = StreamingToolGuard()
        narrative_parts = []
        found_calls = []

        for chunk in chunks:
            delta, c = guard.feed(chunk)
            if delta:
                narrative_parts.append(delta)
            found_calls.extend(c)

        tail, c = guard.finish()
        if tail:
            narrative_parts.append(tail)
        found_calls.extend(c)

        narrative = "".join(narrative_parts)
        assert len(found_calls) == 1
        assert found_calls[0].name == "list_dir"
        assert found_calls[0].arguments == {"subpath": "Source/CounterStrike"}
        assert "Checking directory structure." in narrative
        assert "Directory listed." in narrative
        assert '"command"' not in narrative


def test_code_fence_json_not_executed():
    """Verify that JSON example blocks inside markdown code fences are NEVER parsed as tool calls."""
    markdown_doc = (
        "Here is an example config:\n\n"
        "```json\n"
        '{\n  "command": "read_file",\n  "path": "Config/DefaultEngine.ini"\n}\n'
        "```\n\n"
        "You can use this syntax."
    )
    res = parse_text_for_tool_calls(markdown_doc)
    assert len(res.calls) == 0
    assert "```json" in res.cleaned_text
    assert '"command": "read_file"' in res.cleaned_text


def test_escaped_quotes_and_braces_in_arguments():
    """Verify that braces and escaped quotes inside JSON string values do not break scanning."""
    text = (
        '{\n  "tool": "write_file",\n  "args": {\n    "subpath": "test.txt",\n'
        '    "content": "function() { return \\"hello {world}\\"; }"\n  }\n}'
    )
    res = parse_text_for_tool_calls(text)
    assert len(res.calls) == 1
    call = res.calls[0]
    assert call.name == "write_file"
    assert call.arguments["content"] == 'function() { return "hello {world}"; }'


def test_multiple_tool_calls_in_single_turn():
    """Verify that multiple tool calls in one turn are extracted in order."""
    text = (
        '{\n  "command": "read_file",\n  "path": "FileA.cpp"\n}\n\n'
        '{\n  "command": "read_file",\n  "path": "FileB.cpp"\n}'
    )
    res = parse_text_for_tool_calls(text)
    assert len(res.calls) == 2
    assert res.calls[0].arguments["path"] == "FileA.cpp"
    assert res.calls[1].arguments["path"] == "FileB.cpp"


def test_unknown_command_not_executed():
    """Verify that unknown commands are not executed as tools and remain safe narrative."""
    text = '{\n  "command": "format_c_drive",\n  "target": "C:\\\\"\n}'
    res = parse_text_for_tool_calls(text)
    assert len(res.calls) == 0
    assert "format_c_drive" in res.cleaned_text
