"""Regression tests for genre classification, board game presets, and layout fallback."""
from __future__ import annotations

import json
from unittest.mock import MagicMock
import urllib.request

import pytest

from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider
from src.gameforge_ide.composer.compose import compose
from src.gameforge_ide.design.draft import DesignDraft, DraftEntity, DraftWin, DraftLose
from src.gameforge_ide.design.expand import expand_draft
from src.gameforge_ide.design.gds import CameraKind, EntityKind, GameDesignSpec, Genre, LevelSpec
from src.gameforge_ide.design.presets import PRESETS, PRESET_KEYWORDS, preset_grid_board
from src.gameforge_ide.design.prompt_to_gds import DRAFT_SYSTEM_PROMPT, prompt_to_gds


def _is_ollama_available() -> bool:
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def test_grid_board_preset_creation():
    """Test that preset_grid_board generates the required schema, props, and genre."""
    gds = preset_grid_board()
    assert gds.overview.genre == Genre.GRID_BOARD
    assert gds.overview.camera == CameraKind.FIXED_BOARD
    assert gds.overview.players in (1, 2)

    board = next((e for e in gds.entities if e.kind == EntityKind.BOARD), None)
    assert board is not None
    assert board.props["board_size"] >= 3


def test_make_grid_board_prompt_classification():
    """Test 'make a turn-based board game' routes to genre grid_board."""
    res = prompt_to_gds("make a turn-based board game")
    assert res.status == "OK"
    assert res.gds is not None
    assert res.gds.overview.genre == Genre.GRID_BOARD


@pytest.mark.parametrize("kw", [
    "board game",
    "dice board game",
    "turn-based board game",
])
def test_board_game_classification_keywords(kw):
    """Test that generic board game prompts map to grid_board."""
    res = prompt_to_gds(f"create a {kw} for family night")
    assert res.status == "OK"
    assert res.gds is not None
    assert res.gds.overview.genre == Genre.GRID_BOARD


def test_platformer_classification():
    """Test 'make a platformer game' routes to genre platformer."""
    res = prompt_to_gds("make a platformer game")
    assert res.status == "OK"
    assert res.gds is not None
    assert res.gds.overview.genre == Genre.PLATFORMER


def test_tactical_fps_not_platformer():
    """Test 'make a tactical fps' is NOT classified as genre platformer."""
    # Preset path check
    res = prompt_to_gds("make a tactical fps", allow_model=False)
    # Tactical FPS is not a platformer preset
    if res.gds is not None:
        assert res.gds.overview.genre != Genre.PLATFORMER

    # Model path check with mock
    mock_complete = MagicMock(return_value=json.dumps({
        "title": "Tactical FPS",
        "genre": "custom",
        "camera": "first_person",
        "win": [{"type": "defeat_all", "target": 5}],
    }))
    res_model = prompt_to_gds(
        "make a tactical fps",
        complete_json=mock_complete,
        model="gameforge-qwen3.5-9b",
    )
    assert res_model.gds is not None
    assert res_model.gds.overview.genre != Genre.PLATFORMER


def test_chess_game_through_model_path_mock():
    """Test 'chess game' routes through model path and receives grid_board guidance."""
    captured_system = []

    def fake_complete(system_prompt, user_prompt, schema):
        captured_system.append(system_prompt)
        assert "grid_board" in system_prompt
        assert "chess" in system_prompt
        return json.dumps({
            "title": "Chess",
            "genre": "grid_board",
            "camera": "fixed_board",
            "pitch": "Classic 8x8 chess strategy game",
            "win": [{"type": "board_win"}],
            "lose": [{"type": "board_loss"}],
        })

    res = prompt_to_gds(
        "chess game",
        complete_json=fake_complete,
        model="gameforge-qwen3.5-9b",
    )
    assert res.status == "OK"
    assert res.path == "model"
    assert res.gds is not None
    assert res.gds.overview.genre == Genre.GRID_BOARD
    assert len(captured_system) == 1
    assert "chess" in captured_system[0].lower()


def test_chess_game_live_ollama():
    """Live Ollama test verifying gameforge-qwen3.5-9b classifies chess game as grid_board."""
    if not _is_ollama_available():
        pytest.skip("Ollama service not running at 127.0.0.1:11434")

    provider = OllamaProvider()
    res = prompt_to_gds(
        "chess game",
        complete_json=lambda sys, usr, sch: provider.complete_json("gameforge-qwen3.5-9b", sys, usr, sch),
        model="gameforge-qwen3.5-9b",
    )
    assert res.status in ("OK", "NEEDS_INPUT")
    assert res.gds is not None
    assert res.gds.overview.genre == Genre.GRID_BOARD


def test_monopoly_live_or_mock():
    """Test 'monopoly' classifies to genre grid_board."""
    if _is_ollama_available():
        provider = OllamaProvider()
        res = prompt_to_gds(
            "make a monopoly board game",
            complete_json=lambda sys, usr, sch: provider.complete_json("gameforge-qwen3.5-9b", sys, usr, sch),
            model="gameforge-qwen3.5-9b",
        )
        assert res.gds is not None
        assert res.gds.overview.genre == Genre.GRID_BOARD
    else:
        mock_complete = MagicMock(return_value=json.dumps({
            "title": "Monopoly",
            "genre": "grid_board",
            "camera": "fixed_board",
            "pitch": "Property trading board game",
            "win": [{"type": "score_at_least", "target": 1000}],
        }))
        res = prompt_to_gds("make a monopoly board game", complete_json=mock_complete, model="test-model")
        assert res.gds is not None
        assert res.gds.overview.genre == Genre.GRID_BOARD


def test_compose_layout_fallback():
    """Test composer layout fallback selects board for grid_board and lanes for card_battler."""
    from unittest.mock import MagicMock

    mock_board = MagicMock()
    mock_board.entities = []
    mock_board.rules = []
    mock_board.overview.genre = Genre.GRID_BOARD
    mock_board.overview.camera = CameraKind.FIXED_BOARD
    mock_board.overview.pitch = ""
    mock_board.meta.title = "Board Test"
    mock_board.meta.project_name = "BoardTest"
    mock_board.meta.source_prompt = ""
    mock_board.meta.id = "gds_123456789012"
    mock_board.meta.gds_id = "gds_123456789012"
    mock_board.scene.levels = []
    comp_board = compose(mock_board)
    assert comp_board.levels[0].level_id == "level_1"
    assert any("GF_Board" in a.tags for a in comp_board.levels[0].actors)

    mock_card = MagicMock()
    mock_card.entities = []
    mock_card.rules = []
    mock_card.overview.genre = Genre.CARD_BATTLER
    mock_card.overview.camera = CameraKind.FIXED_BOARD
    mock_card.overview.pitch = ""
    mock_card.meta.title = "Card Test"
    mock_card.meta.project_name = "CardTest"
    mock_card.meta.source_prompt = ""
    mock_card.meta.id = "gds_123456789012"
    mock_card.meta.gds_id = "gds_123456789012"
    mock_card.scene.levels = []
    comp_card = compose(mock_card)
    assert comp_card.levels[0].level_id == "level_1"
    assert any("GF_CardTable" in a.tags for a in comp_card.levels[0].actors)


def test_expand_players_count_logic():
    """Test expand_draft sets players count correctly based on genre and entity props."""
    # GRID_BOARD defaults to players=2
    draft_board = DesignDraft(
        title="Checkers",
        genre=Genre.GRID_BOARD,
        camera=CameraKind.FIXED_BOARD,
        pitch="Checkers game",
        win=[DraftWin(type="board_win")],
    )
    gds_board = expand_draft(draft_board)
    assert gds_board.overview.players == 2

    # PLATFORMER defaults to players=1
    draft_plat = DesignDraft(
        title="Jump",
        genre=Genre.PLATFORMER,
        camera=CameraKind.THIRD_PERSON,
        pitch="Jump game",
        win=[DraftWin(type="reach_goal")],
    )
    gds_plat = expand_draft(draft_plat)
    assert gds_plat.overview.players == 1

    # Board entity with explicit players=4
    gds_board_4 = preset_grid_board(players=4)
    assert gds_board_4.overview.players == 4
