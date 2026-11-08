"""Unit tests for prompt_to_gds orchestration and OllamaProvider.complete_json (P1 WI-1.6)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider
from src.gameforge_ide.design.draft import DesignDraft
from src.gameforge_ide.design.gds import CameraKind, Genre
from src.gameforge_ide.design.prompt_to_gds import (
    DRAFT_SYSTEM_PROMPT,
    PromptToGdsResult,
    prompt_to_gds,
)


def test_unsupported_prompt():
    res = prompt_to_gds("fix the build error in Foo.cpp")
    assert res.status == "UNSUPPORTED"
    assert res.path == "none"
    assert res.gds is None
    assert len(res.errors) >= 1


def test_preset_path_no_model_called():
    mock_complete = MagicMock()
    res = prompt_to_gds(
        "make a 3d platformer with 8 coins called Sky Hop",
        complete_json=mock_complete,
        allow_model=True,
    )
    assert res.status == "OK"
    assert res.path == "preset"
    assert res.gds is not None
    assert res.gds.meta.title == "Sky Hop"
    mock_complete.assert_not_called()

    # Verify pickups count
    pickups = [e for e in res.gds.entities if e.kind.value == "pickup"]
    assert len(pickups) == 1
    assert pickups[0].count == 8


def test_preset_tic_tac_toe():
    res = prompt_to_gds("create a tic tac toe game against a friend")
    assert res.status == "OK"
    assert res.path == "preset"
    assert res.gds is not None
    board = [e for e in res.gds.entities if e.kind.value == "board"][0]
    assert board.props.get("board_size") == 3
    assert board.props.get("vs_ai") is False


def test_model_path_valid():
    valid_draft = {
        "title": "Stealth Infiltrator",
        "genre": "exploration",
        "camera": "third_person",
        "pitch": "Sneak past guards to steal relics",
        "entities": [
            {"kind": "guard", "count": 3, "note": "patrol"},
            {"kind": "pickup", "count": 5, "note": "relics"},
        ],
        "win": [{"type": "collect_all", "target": 5}],
        "lose": [{"type": "caught_by_guard"}],
    }

    mock_complete = MagicMock(side_effect=[None, json.dumps(valid_draft)])
    res = prompt_to_gds(
        "make a stealth adventure game where you avoid guards and collect relics",
        complete_json=mock_complete,
        model="gameforge-qwen3.5-9b",
    )
    assert res.status == "OK"
    assert res.path == "model"
    assert res.gds is not None
    assert res.attempts == 1
    assert res.gds.meta.title == "Stealth Infiltrator"
    assert mock_complete.call_count == 2


def test_model_path_repair_call_on_invalid_json():
    # Attempt 1 returns broken JSON, Attempt 2 returns valid draft
    valid_draft = {
        "title": "Dungeon Crawler",
        "genre": "dungeon_crawler",
        "camera": "third_person",
        "pitch": "Clear enemies and survive",
        "entities": [{"kind": "enemy", "count": 4, "note": "skeletons"}],
        "win": [{"type": "defeat_all"}],
        "lose": [{"type": "health_zero"}],
    }

    mock_complete = MagicMock(side_effect=[
        None,                                             # strategy evaluator: no structured decision
        '{"title": "Broken", "genre": "NOT_A_GENRE"}',  # invalid draft
        json.dumps(valid_draft),                         # repaired draft
    ])

    res = prompt_to_gds(
        "create a dungeon crawler game slaying monsters",
        complete_json=mock_complete,
        model="gameforge-qwen3.5-9b",
    )
    assert res.status == "OK"
    assert res.path == "model"
    assert res.attempts == 2
    assert len(res.errors) == 1
    assert "Attempt 1" in res.errors[0]
    assert res.gds is not None
    assert res.gds.meta.title == "Dungeon Crawler"
    assert mock_complete.call_count == 3


def test_model_path_still_invalid_after_repair():
    mock_complete = MagicMock(side_effect=[
        None,                         # strategy evaluator fallback
        "{not valid json",
        '{"invalid": "still bad schema"}',
    ])

    res = prompt_to_gds(
        "make an action game with space aliens",
        complete_json=mock_complete,
        model="gameforge-qwen3.5-9b",
    )
    assert res.status == "NEEDS_INPUT"
    assert res.path == "model"
    assert res.attempts == 2
    assert len(res.errors) == 2
    assert len(res.questions) >= 1
    assert res.gds is None


def test_model_path_with_draft_questions():
    draft_with_q = {
        "title": "Space Explorer",
        "genre": "exploration",
        "camera": "third_person",
        "pitch": "Fly around asteroids",
        "win": [{"type": "survive_seconds", "target": 60}],
        "questions": ["Should there be hostile ships or peace mode?"],
    }
    mock_complete = MagicMock(side_effect=[None, json.dumps(draft_with_q)])
    res = prompt_to_gds(
        "make an exploration game in an asteroid field",
        complete_json=mock_complete,
    )
    assert res.status == "NEEDS_INPUT"
    assert res.path == "model"
    assert res.questions == ["Should there be hostile ships or peace mode?"]
    # Handover spec: "A valid draft with questions non-empty -> NEEDS_INPUT with those questions, and also the expanded GDS"
    assert res.gds is not None


def test_no_model_available():
    res = prompt_to_gds("make a space adventure game", complete_json=None)
    assert res.status == "NEEDS_INPUT"
    assert res.path == "none"
    assert res.gds is None
    assert "Which kind of game is this closest to" in res.questions[0]


def test_ollama_provider_complete_json():
    provider = OllamaProvider(host="127.0.0.1:11434")
    mock_resp_data = {
        "message": {"role": "assistant", "content": '{"title": "Test"}'}
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = provider.complete_json(
            model_id="test-model",
            system="System prompt",
            user="User prompt",
            schema={"type": "object"},
        )
        assert result == '{"title": "Test"}'
        assert mock_urlopen.call_count == 1
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://127.0.0.1:11434/api/chat"
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["model"] == "test-model"
        assert payload["think"] is False
        assert payload["stream"] is False
        assert payload["format"] == {"type": "object"}
        assert payload["options"]["num_ctx"] == 8192


def test_scratch_fallback_has_truthful_generator_provenance():
    """A deterministic scratch fallback must never claim the LLM generated it."""
    res = prompt_to_gds(
        "create a Sudoku game",
        complete_json=lambda system, user, schema: None,
        model="gameforge-qwen3.5-9b",
        allow_model=True,
    )
    assert res.status == "OK"
    assert res.path == "preset"
    assert res.gds is not None
    assert res.gds.meta.generator == "fallback:scratch"
    assert any("deterministic" in error.lower() for error in res.errors)


def test_sudoku_strategy_never_selects_incompatible_template():
    """A Sudoku request must remain a dedicated puzzle/scratch architecture."""
    strategy_response = json.dumps({
        "strategy": "adapt_template",
        "template_id": "platformer_3d",
        "reasoning": "intentionally incompatible test response",
    })
    res = prompt_to_gds(
        "create a Sudoku game",
        complete_json=lambda system, user, schema: strategy_response,
        model="gameforge-qwen3.5-9b",
        allow_model=True,
    )
    assert res.status == "OK"
    assert res.gds is not None
    assert res.gds.overview.genre == Genre.PUZZLE
    assert res.gds.overview.camera == CameraKind.FIXED_BOARD
    assert res.gds.meta.generator == "fallback:scratch"
