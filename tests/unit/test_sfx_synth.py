"""Roadmap M14 step 1: procedural SFX synthesizer."""

import pytest

from src.gameforge_ide.backend.assets.registry import AssetRegistry
from src.gameforge_ide.backend.tools.sfx_synth import KINDS, SFXSpec, analyze_wav, generate_sfx, synthesize


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_is_valid_headroomed_audio(kind, tmp_path):
    info = generate_sfx(SFXSpec(name=f"T_{kind}", kind=kind, seed=3), tmp_path)
    a = info["analysis"]
    assert a["sample_rate"] == 44100 and a["channels"] == 1 and a["bits"] == 16
    assert a["duration_s"] > 0.02 and a["clipped_samples"] == 0
    assert 0.5 < a["peak"] <= 0.81 and a["rms"] > 0.01
    assert info["provenance"] == "procedural"


def test_wind_loop_has_no_seam(tmp_path):
    info = generate_sfx(SFXSpec(name="Wind", kind="wind_loop", seed=1), tmp_path)
    assert info["looping"] and info["analysis"]["loop_seam_ratio"] < 3.0


def test_deterministic_per_seed():
    a = synthesize(SFXSpec(name="A", kind="impact", seed=5))
    b = synthesize(SFXSpec(name="A", kind="impact", seed=5))
    c = synthesize(SFXSpec(name="A", kind="impact", seed=6))
    assert (a == b).all() and not (a == c).all()


@pytest.mark.parametrize("kw", [{"kind": "explosion"}, {"gain": 1.0}, {"name": "bad name"}, {"duration_s": 60}])
def test_invalid_specs_rejected(kw):
    with pytest.raises(ValueError):
        synthesize(SFXSpec(**{"name": "X", "kind": "click", **kw}))


def test_registry_row(tmp_path):
    reg = AssetRegistry(tmp_path / "ws")
    info = generate_sfx(SFXSpec(name="Chime", kind="pickup"), tmp_path / "out", reg)
    row = reg.get(info["registry_id"])
    assert row["asset_type"] == "sound" and row["provenance"] == "procedural" and reg.artifact_unchanged(row["asset_id"])
    assert analyze_wav(info["path"])["duration_s"] == pytest.approx(0.35, abs=0.01)
