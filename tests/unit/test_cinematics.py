"""Unit tests for in-game intro cinematics generator (WI-10.5)."""
from pathlib import Path
import pytest

from src.gameforge_ide.composer.cinematics import generate_intro_cinematic
from src.gameforge_ide.design.presets import get_preset_spec


def test_cinematic_generation_defaults():
    gds = get_preset_spec("relic_hunt")
    seq = generate_intro_cinematic(gds)
    
    assert seq["sequence_name"] == f"LS_{gds.meta.project_name}_Intro"
    assert seq["duration_seconds"] == 8.0
    assert seq["fps"] == 30
    assert len(seq["shots"]) == 3
    assert seq["cut_count"] == 3
    assert seq["playback_policy"]["skippable"] is True


def test_cinematic_custom_intro():
    gds = get_preset_spec("relic_hunt")
    gds.presentation.intro.enabled = True
    gds.presentation.intro.seconds = 14.0
    gds.presentation.intro.focus = ["landmark", "goal"]

    seq = generate_intro_cinematic(gds)
    assert seq["duration_seconds"] == 14.0
    assert seq["total_frames"] == 14 * 30
    assert seq["keyframes_count"] == 14 * 30
