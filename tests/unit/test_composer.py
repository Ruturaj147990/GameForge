"""Comprehensive unit tests for Composer (Phase 6, WI-6.1 to WI-6.10)."""
from __future__ import annotations

import pytest

from src.gameforge_ide.composer import (
    CodegenTask,
    Composition,
    CompositionError,
    LevelPlan,
    OpCall,
    PlacedActor,
    compose,
    plan_to_op_calls,
    composition_to_run_spec,
)
from src.gameforge_ide.composer.codegen import (
    generate_header,
    generate_source,
    safety_scan,
)
from src.gameforge_ide.composer.layouts.course import validate_jump_reachability
from src.gameforge_ide.composer.placement import is_point_in_polygon, scatter, along_path
from src.gameforge_ide.design.presets import PRESETS, preset_tic_tac_toe, preset_platformer
import random


def test_composer_determinism():
    """compose(gds) must produce byte-identical model_dump_json() across calls."""
    gds = preset_tic_tac_toe()
    c1 = compose(gds).model_dump_json()
    c2 = compose(gds).model_dump_json()
    assert c1 == c2


def test_all_presets_compose_and_emit_valid_ops():
    """All 9 preset genres compose and emit strictly schema-valid OpCalls."""
    for name, factory in PRESETS.items():
        gds = factory()
        comp = compose(gds)
        assert comp.project_name
        assert len(comp.levels) >= 1
        assert len(comp.modules) >= 1

        for level in comp.levels:
            ops = plan_to_op_calls(level, comp.gfdef)
            assert len(ops) >= 5
            # Each op must have valid op name
            for op in ops:
                assert op.op
                assert isinstance(op.args, dict)


def test_ballistic_jump_reachability():
    """Test jump ballistic formula for reachability and failure cases."""
    # Standard jumpable gap and height (v=650, g=1.2, speed=600 -> max_h ~ 179.7cm)
    reachable, max_h, max_g = validate_jump_reachability(gap_cm=300.0, height_delta_cm=50.0)
    assert reachable is True
    assert max_h > 100.0
    assert max_g > 300.0

    # Impossible height (e.g. 300cm high)
    reachable_high, _, _ = validate_jump_reachability(gap_cm=100.0, height_delta_cm=300.0)
    assert reachable_high is False

    # Impossible gap (e.g. 1500cm wide)
    reachable_far, _, _ = validate_jump_reachability(gap_cm=1500.0, height_delta_cm=0.0)
    assert reachable_far is False


def test_poisson_scatter_and_path():
    """Test Poisson-disk scatter inside polygon with avoidance zones."""
    poly = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0)]
    assert is_point_in_polygon((500.0, 500.0), poly) is True
    assert is_point_in_polygon((1500.0, 500.0), poly) is False

    rng = random.Random(42)
    avoid = [(500.0, 500.0, 150.0)]
    pts, warn = scatter(poly, n=6, min_spacing_cm=120.0, rng=rng, avoid=avoid)
    assert len(pts) == 6
    assert warn is None
    for px, py in pts:
        assert 0.0 <= px <= 1000.0
        assert 0.0 <= py <= 1000.0
        # Check avoid zone
        dist_sq = (px - 500.0) ** 2 + (py - 500.0) ** 2
        assert dist_sq >= 150.0 ** 2

    # Arc-length path placement
    path = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 100.0, 0.0)]
    samples = along_path(path, n=3)
    assert len(samples) == 3
    assert samples[0] == (0.0, 0.0, 0.0)
    assert samples[-1] == (100.0, 100.0, 0.0)


def test_composition_to_run_spec():
    """Verify that composition_to_run_spec generates a DAG-compliant RunSpec."""
    gds = preset_platformer()
    comp = compose(gds)
    run_spec = composition_to_run_spec(comp, workspace_dir="E:/GameForge")

    assert run_spec.title
    step_ids = [s.step_id for s in run_spec.steps]
    assert "design" in step_ids
    assert "scaffold" in step_ids
    assert "build_editor" in step_ids
    assert "content" in step_ids
    assert "package" in step_ids
    assert "scenarios" in step_ids


def test_codegen_safety_and_skeletons():
    """Verify C++ codegen safety scanner blocks dangerous symbols."""
    clean_code = "GameState()->SetStat(FName(TEXT('score')), 10.0f);"
    ok, errs = safety_scan(clean_code)
    assert ok is True
    assert not errs

    bad_code = "#include <windows.h>\nFPlatformProcess::Sleep(5);"
    ok_bad, errs_bad = safety_scan(bad_code)
    assert ok_bad is False
    assert len(errs_bad) >= 2

    # Skeleton generation
    hdr = generate_header("MyGame", "Custom0Rule")
    assert "class MYGAME_API UCustom0Rule : public UGameForgeCustomRule" in hdr
    src = generate_source("Custom0Rule", on_event_body="// event logic", tick_body="// tick logic")
    assert "void UCustom0Rule::OnEvent" in src
    assert "// BEGIN MODEL CODE" in src
