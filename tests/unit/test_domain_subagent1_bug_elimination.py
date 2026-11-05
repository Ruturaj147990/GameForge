"""Unit tests for Non-Frontend Bug Elimination across Subagent 1 domain.

Covers:
1. Provider reliability (Ollama empty body, streaming error record, tool error).
2. Hosted provider SSE error and empty body retry.
3. Agent loop tool execution exception resilience, tool arg parsing (escaped JSON, code fences, raw strings),
   cooperative task cancellation, phantom edit and narrative excuse regexes.
4. GDS negative prompt constraints (no enemies, no guns, no timer, negated mechanics).
5. Semantic validation of contradictory win/lose conditions.
6. Patch application boundary checks and RFC 6902 replace validation.
"""
from __future__ import annotations

import asyncio
import json
import io
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider
from src.gameforge_ide.backend.providers.hosted import _post_json, OpenAICompatibleHostedProvider, HostedProfile
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.backend.providers.router import ModelRouter
from src.gameforge_ide.design.gds import GameDesignSpec, Genre, CameraKind
from src.gameforge_ide.design.presets import preset_platformer, preset_arena_combat
from src.gameforge_ide.design.patch import apply_patch, PatchError
from src.gameforge_ide.design.patch_rules import match_deterministic_rule
from src.gameforge_ide.design.semantic_validate import semantic_validate_gds
from src.gameforge_ide.design.intent import extract_gameplay_mechanics


# ── 1. Provider Reliability Tests ─────────────────────────────────────────────

def test_ollama_parse_stream_lines_error_chunk():
    """Verify Ollama error JSON record yields StreamChunk with error and is_final=True."""
    lines = [
        b'{"response": "token 1", "done": false}\n',
        b'{"error": "model \'missing\' not found"}\n',
    ]
    chunks = list(OllamaProvider.parse_stream_lines(lines))
    assert len(chunks) == 2
    assert chunks[0].token == "token 1"
    assert chunks[0].is_final is False
    assert chunks[1].is_final is True
    assert "model 'missing' not found" in chunks[1].error


def test_ollama_parse_stream_lines_status_chunks_not_empty_tokens():
    """Verify status lines (e.g. model loading) do not yield blank empty token chunks."""
    lines = [
        b'{"status": "loading model into VRAM"}\n',
        b'{"response": "Hello", "done": false}\n',
        b'{"response": " world", "done": true, "eval_count": 2}\n',
    ]
    chunks = list(OllamaProvider.parse_stream_lines(lines))
    # Chunks with tokens or finality or status metadata
    tokens = [c.token for c in chunks if c.token]
    assert tokens == ["Hello", " world"]
    assert chunks[-1].is_final is True


def test_ollama_parse_stream_lines_severed_stream_finalizes():
    """Verify stream ending without done=True still emits a final chunk."""
    lines = [
        b'{"response": "cut off"}',
    ]
    chunks = list(OllamaProvider.parse_stream_lines(lines))
    assert len(chunks) == 2
    assert chunks[0].token == "cut off"
    assert chunks[1].is_final is True


def test_ollama_request_with_retry_empty_body():
    """Verify empty response body triggers retries and does not crash with raw JSONDecodeError."""
    provider = OllamaProvider()
    req = MagicMock()
    # Mock urlopen returning empty bytes then valid json
    resp_empty = io.BytesIO(b"")
    resp_valid = io.BytesIO(b'{"response": "ok"}')

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [resp_empty, resp_valid]
        result = provider._request_with_retry(req, timeout=1.0, max_retries=2)
        assert result.get("response") == "ok"


def test_ollama_chat_with_tools_raises_on_api_error():
    """Verify chat_with_tools raises RuntimeError when Ollama API returns error."""
    provider = OllamaProvider()
    with patch.object(provider, "_request_with_retry", return_value={"error": "cuda out of memory"}):
        with pytest.raises(RuntimeError, match="Ollama API error: cuda out of memory"):
            provider.chat_with_tools("test-model", [], [])


def test_hosted_post_json_empty_body_retries():
    """Verify _post_json retries on empty response body."""
    resp_empty = io.BytesIO(b"")
    resp_valid = io.BytesIO(b'{"id": "resp-1"}')

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [resp_empty, resp_valid]
        res = _post_json("http://fake.api/v1", {}, {}, timeout=1.0)
        assert res.get("id") == "resp-1"


# ── 2. Agent Loop Edge Cases Tests ─────────────────────────────────────────────

def test_extract_tool_call_escaped_string_arguments(tmp_path: Path):
    """Verify tool call extraction handles escaped JSON string arguments."""
    runtime = AgentRuntime(tmp_path, SessionManager(tmp_path), ModelRouter())
    raw = '{"tool": "read_file", "args": "{\\"subpath\\": \\"Source/Game.cpp\\"}"}'
    call = runtime._extract_tool_call(raw)
    assert call is not None
    assert call["name"] == "read_file"
    assert call["arguments"] == {"subpath": "Source/Game.cpp"}


def test_extract_tool_call_markdown_fenced_arguments(tmp_path: Path):
    """Verify tool call extraction handles arguments inside markdown code fences."""
    runtime = AgentRuntime(tmp_path, SessionManager(tmp_path), ModelRouter())
    raw = '{"tool": "propose_edit", "args": "```json\\n{\\"subpath\\": \\"Game.h\\", \\"target\\": \\"a\\", \\"replacement\\": \\"b\\"}\\n```"}'
    call = runtime._extract_tool_call(raw)
    assert call is not None
    assert call["name"] == "propose_edit"
    assert call["arguments"]["subpath"] == "Game.h"


def test_extract_tool_call_raw_string_argument(tmp_path: Path):
    """Verify tool call extraction preserves raw string argument without crashing."""
    runtime = AgentRuntime(tmp_path, SessionManager(tmp_path), ModelRouter())
    raw = '{"tool": "list_dir", "args": "Source/Game"}'
    call = runtime._extract_tool_call(raw)
    assert call is not None
    assert call["arguments"] == {"input": "Source/Game"}


def test_detect_phantom_edit_expanded_adverbs(tmp_path: Path):
    """Verify phantom edit detection catches edits with adverbs and diverse phrasing."""
    assert AgentRuntime._detect_phantom_edit_or_claimed_modification(
        "I have successfully updated the file with the requested changes."
    )
    assert AgentRuntime._detect_phantom_edit_or_claimed_modification(
        "I have already modified the code to fix the issue."
    )
    assert AgentRuntime._detect_phantom_edit_or_claimed_modification(
        "The file is now updated with the implementation."
    )
    assert AgentRuntime._detect_phantom_edit_or_claimed_modification(
        "Below is the updated code for your review."
    )
    assert AgentRuntime._detect_phantom_edit_or_claimed_modification(
        "I have finished the implementation of the game mode."
    )


def test_is_narrative_excuse_expanded_phrasing(tmp_path: Path):
    """Verify narrative excuse detection catches refusal/access patterns."""
    assert AgentRuntime._is_narrative_excuse(
        "I do not have permission to write to this directory."
    )
    assert AgentRuntime._is_narrative_excuse(
        "I'm an AI and I cannot directly edit your files."
    )
    assert AgentRuntime._is_narrative_excuse(
        "I am not able to proceed with this task due to an error."
    )


@pytest.mark.anyio
async def test_runtime_catches_tool_execution_exception(tmp_path: Path):
    """Verify runtime does not crash when tool execution raises an unexpected exception."""
    sm = SessionManager(tmp_path)
    session = sm.create_session("ExTest")
    runtime = AgentRuntime(tmp_path, sm, ModelRouter())

    # Mock tool gateway to raise an unexpected exception
    with patch.object(runtime.tool_gateway, "execute_tool", side_effect=PermissionError("Access denied to OS path")):
        # Mock provider chat_with_tools to invoke list_dir
        mock_provider = MagicMock()
        mock_provider.get_capabilities.return_value = MagicMock(max_context=4096)
        mock_provider.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [{"name": "list_dir", "arguments": {"subpath": "."}}],
        }
        with patch.object(runtime.router, "get_provider", return_value=mock_provider):
            events = []
            async for ev in runtime.execute_task_stream(session.session_id, "Inspect files"):
                events.append(ev)

            # Ensure tool_result was emitted with ERROR status and stream did not crash
            result_ev = next((e for e in events if e.event_type == "tool_result"), None)
            assert result_ev is not None
            assert result_ev.metadata["result"]["status"] == "ERROR"
            assert "PermissionError" in result_ev.metadata["result"]["error"]


@pytest.mark.anyio
async def test_runtime_cooperative_cancellation(tmp_path: Path):
    """Verify cancel_task marks task state as CANCELLED and halts cleanly."""
    sm = SessionManager(tmp_path)
    session = sm.create_session("CancelTest")
    runtime = AgentRuntime(tmp_path, sm, ModelRouter())

    runtime.cancel_task(session.session_id)
    assert runtime.is_task_cancelled(session.session_id)


# ── 3. GDS & Patch Negative Constraints Tests ─────────────────────────────────

def test_intent_extract_gameplay_mechanics_filters_negated():
    """Verify negated mechanics like 'no timer' or 'without hazards' are not extracted as features."""
    prompt = "Create a 3D platformer without hazards, no timer, and no permadeath with double jump."
    mechanics = extract_gameplay_mechanics(prompt)
    assert "timer" not in mechanics
    assert "hazard" not in mechanics
    assert "permadeath" not in mechanics
    assert "double jump" in mechanics


def test_patch_rules_without_enemies_does_not_add_combat():
    """Verify 'without enemies' or 'no combat' never triggers _match_complete_game_or_add_combat."""
    gds = preset_platformer()
    patch = match_deterministic_rule(gds, "complete the platformer without enemies")
    # Must NOT add an enemy spawner!
    if patch:
        spawner_ops = [op for op in patch.ops if "spawner" in str(op.get("value", ""))]
        assert len(spawner_ops) == 0


def test_patch_rules_no_enemies_removes_enemies():
    """Verify 'no enemies' or 'without enemies' triggers remove patch on enemy entities."""
    gds = preset_arena_combat()
    patch = match_deterministic_rule(gds, "no enemies")
    assert patch is not None
    assert any(op.get("op") == "remove" and "/entities/" in op.get("path", "") for op in patch.ops)


def test_patch_rules_no_timer_removes_timer():
    """Verify 'no timer' or 'without timer' removes timer from goals.lose."""
    gds = preset_platformer()
    # Add a timer
    gds.goals.lose.append({"kind": "timer", "seconds": 60.0})
    patch = match_deterministic_rule(gds, "no timer")
    assert patch is not None
    assert any(op.get("op") == "remove" and "/goals/lose/" in op.get("path", "") for op in patch.ops)


def test_patch_rules_remove_weapons():
    """Verify 'no guns' or 'remove weapons' strips weapons and attack mode."""
    from src.gameforge_ide.design.gds import EntityKind
    gds = preset_arena_combat()
    # Configure player with weapons
    player = next(e for e in gds.entities if e.kind == EntityKind.PLAYER)
    player.props["weapons"] = ["rifle", "pistol"]
    player.props["attack_mode"] = "projectile"
    patch = match_deterministic_rule(gds, "remove weapons from player")
    assert patch is not None
    assert any("weapons" in op.get("path", "") for op in patch.ops)


# ── 4. Semantic Validation Contradictory Goals Tests ──────────────────────────

def test_semantic_validate_detects_contradictory_score_goals():
    """Verify semantic validation catches contradictory score goals (score >= 10 and score <= 0)."""
    gds = preset_platformer()
    gds.goals.win = [{"kind": "stat", "stat": "game.score", "op": ">=", "value": 10.0}]
    gds.goals.lose = [{"kind": "stat", "stat": "game.score", "op": "<=", "value": 0.0}]

    valid, issues = semantic_validate_gds(gds, "A 3D platformer with score")
    assert not valid
    assert any("Contradictory goals" in i for i in issues)


def test_semantic_validate_detects_identical_win_and_lose_condition():
    """Verify semantic validation catches identical condition in both win and lose."""
    gds = preset_platformer()
    gds.goals.win = [{"kind": "stat", "stat": "game.score", "op": ">=", "value": 50.0}]
    gds.goals.lose = [{"kind": "stat", "stat": "game.score", "op": ">=", "value": 50.0}]

    valid, issues = semantic_validate_gds(gds, "A platformer game")
    assert not valid
    assert any("both trigger when 'game.score >= 50.0'" in i for i in issues)


def test_semantic_validate_detects_negative_prompt_violation():
    """Verify semantic validation catches when prompt requested 'no enemies' but GDS has enemies."""
    gds = preset_arena_combat()  # has spawner and enemies
    valid, issues = semantic_validate_gds(gds, "A peaceful game without enemies")
    assert not valid
    assert any("no enemies" in i for i in issues)


# ── 5. Patch Application Boundary Tests ───────────────────────────────────────

def test_apply_patch_nonexistent_item_id_raises_clear_error():
    """Verify replacing or removing a nonexistent entity ID raises clear PatchError."""
    gds = preset_platformer()
    ops = [{"op": "remove", "path": "/entities/nonexistent_boss"}]
    with pytest.raises(PatchError, match="not found in list"):
        apply_patch(gds, ops)


def test_apply_patch_replace_nonexistent_key_raises_error():
    """Verify replace on a nonexistent dict key raises PatchError per RFC 6902."""
    gds = preset_platformer()
    ops = [{"op": "replace", "path": "/entities/0/props/nonexistent_custom_key", "value": 123}]
    with pytest.raises(PatchError, match="does not exist for replace"):
        apply_patch(gds, ops)
