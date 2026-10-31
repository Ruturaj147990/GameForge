"""Unit and property tests for GDS prompt fixtures, drafts, and expander robustness (P1 WI-1.9)."""
from __future__ import annotations

import json
from pathlib import Path
import random
from unittest.mock import MagicMock

import pytest

from src.gameforge_ide.design.draft import (
    DesignDraft,
    DraftEntity,
    DraftLose,
    DraftWin,
)
from src.gameforge_ide.design.expand import ExpandError, expand_draft
from src.gameforge_ide.design.gds import (
    Biome,
    CameraKind,
    EntityKind,
    GameDesignSpec,
    Genre,
)
from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds

FIXTURES_FILE = Path(__file__).resolve().parent.parent / "fixtures" / "gds_prompts.jsonl"
DRAFTS_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "gds_model_drafts"


def _read_fixtures():
    lines = FIXTURES_FILE.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_preset_prompts_deterministic():
    fixtures = _read_fixtures()
    preset_cases = [f for f in fixtures if f["expect"].startswith("preset:")]
    assert len(preset_cases) == 20

    for case in preset_cases:
        prompt = case["prompt"]
        preset_id = case["expect"].split(":", 1)[1]
        checks = case.get("checks", {})

        res = prompt_to_gds(prompt, allow_model=False)
        assert res.status == "OK", f"Failed on prompt: {prompt}"
        assert res.path == "preset"
        assert res.gds is not None

        # Verify checks
        gds = res.gds
        if "title" in checks:
            assert gds.meta.title == checks["title"]
        if "difficulty" in checks:
            assert gds.progression.difficulty == checks["difficulty"]

        if preset_id in ("tic_tac_toe", "connect_four", "gomoku"):
            board = next(e for e in gds.entities if e.kind.value == "board")
            if "board_size" in checks:
                assert board.props.get("board_size") == checks["board_size"]
            if "win_length" in checks:
                assert board.props.get("win_length") == checks["win_length"]
            if "vs_ai" in checks:
                assert board.props.get("vs_ai") == checks["vs_ai"]
            if "gravity" in checks:
                assert board.props.get("gravity") == checks["gravity"]

        elif preset_id == "platformer":
            pickups = next(e for e in gds.entities if e.kind.value == "pickup")
            if "collectible_target" in checks:
                assert pickups.count == checks["collectible_target"]

        elif preset_id == "arena_combat":
            spawner = next(e for e in gds.entities if e.kind.value == "spawner")
            if "wave_count" in checks:
                assert spawner.props.get("wave_count") == checks["wave_count"]
            if "enemies_per_wave" in checks:
                assert spawner.props.get("enemies_per_wave") == checks["enemies_per_wave"]

        elif preset_id == "card_battler":
            table = next(e for e in gds.entities if e.kind.value == "card_table")
            if "player_base_health" in checks:
                assert table.props.get("player_base_health") == checks["player_base_health"]

        elif preset_id == "procedural_world":
            lvl = gds.scene.levels[0]
            if "terrain_type" in checks:
                assert lvl.layout_params.get("terrain_type") == checks["terrain_type"]
            if "foliage_density" in checks:
                assert lvl.layout_params.get("foliage_density") == checks["foliage_density"]
            if "seed" in checks:
                assert lvl.seed == checks["seed"]


def test_unsupported_prompts():
    fixtures = _read_fixtures()
    unsupported_cases = [f for f in fixtures if f["expect"] == "unsupported"]
    assert len(unsupported_cases) == 5

    for case in unsupported_cases:
        prompt = case["prompt"]
        res = prompt_to_gds(prompt)
        assert res.status == "UNSUPPORTED", f"Expected UNSUPPORTED for: {prompt}"
        assert res.path == "none"
        assert res.gds is None


def test_model_path_with_recorded_outputs():
    fixtures = _read_fixtures()
    model_cases = [f for f in fixtures if f["expect"] == "model"]
    assert len(model_cases) == 15

    for i, case in enumerate(model_cases, start=1):
        prompt = case["prompt"]
        draft_file = DRAFTS_DIR / f"draft_{i:02d}.json"
        assert draft_file.is_file(), f"Missing draft file: {draft_file}"
        raw_draft_json = draft_file.read_text(encoding="utf-8")

        mock_complete = MagicMock(return_value=raw_draft_json)
        res = prompt_to_gds(
            prompt,
            complete_json=mock_complete,
            model="gameforge-qwen3.5-9b",
            allow_model=True,
        )

        assert res.status == "OK", f"Prompt {prompt} failed with {res.errors}"
        assert res.path == "model"
        assert res.gds is not None
        assert mock_complete.call_count == 1

        # Check genre matches check
        if "genre" in case.get("checks", {}):
            assert res.gds.overview.genre.value == case["checks"]["genre"]

    # Test deliberately invalid draft triggers exactly one repair call and then NEEDS_INPUT
    broken_complete = MagicMock(side_effect=[
        '{"invalid_schema": true}',  # call 1: invalid
        '{"still_broken": true}',    # call 2 (repair): invalid
    ])

    repair_res = prompt_to_gds(
        "make an action adventure game in space",
        complete_json=broken_complete,
        model="gameforge-qwen3.5-9b",
    )
    assert repair_res.status == "NEEDS_INPUT"
    assert repair_res.path == "model"
    assert repair_res.attempts == 2
    assert broken_complete.call_count == 2
    assert len(repair_res.questions) >= 1


def test_expand_property():
    rng = random.Random(2026)
    genres = list(Genre)
    cameras = list(CameraKind)
    biomes = list(Biome)
    entity_kinds = list(EntityKind)
    win_types = ["collect_all", "reach_goal", "defeat_all", "survive_seconds", "score_at_least", "board_win", "match_win"]
    lose_types = ["health_zero", "timer_runs_out", "fall_off", "board_loss", "match_loss", "caught_by_guard"]

    for i in range(500):
        genre = rng.choice(genres)
        cam = rng.choice(cameras)
        biome = rng.choice(biomes)
        num_ent = rng.randint(0, 3)
        entities = [DraftEntity(kind=rng.choice(entity_kinds), count=rng.randint(1, 10)) for _ in range(num_ent)]
        num_win = rng.randint(1, 2)
        win = [DraftWin(type=rng.choice(win_types), target=rng.randint(1, 20)) for _ in range(num_win)]
        num_lose = rng.randint(0, 2)
        lose = [DraftLose(type=rng.choice(lose_types), seconds=rng.randint(10, 120)) for _ in range(num_lose)]

        draft = DesignDraft(
            title=f"RandomGame{i}",
            genre=genre,
            camera=cam,
            biome=biome,
            entities=entities,
            win=win,
            lose=lose,
        )

        try:
            gds = expand_draft(draft)
            assert isinstance(gds, GameDesignSpec)
        except ExpandError as exc:
            assert exc.question is not None
