"""Unit tests for content audio, music, ambience, and SFX presets (P7 WI-7.8)."""
from pathlib import Path
import numpy as np
import pytest
import wave

from src.gameforge_ide.backend.assets.registry import AssetRegistry
from src.gameforge_ide.content.audio import (
    AudioService,
    crossfade_loop,
    resample_audio,
    verify_audio_loop,
)
from src.gameforge_ide.content.ambience import (
    generate_ambience_loop,
    analyze_ambience_loop,
)
from src.gameforge_ide.content.music import (
    MOOD_CONFIGS,
    analyze_music_loop,
    generate_music_loop,
    note_to_freq,
)
from src.gameforge_ide.content.sfx_presets import (
    SFX_SETS,
    get_sfx_preset,
    list_sfx_presets,
    synthesize_sfx_preset,
)


class TestMusicSynthesis:
    def test_note_to_freq_mathematical_precision(self):
        # A4 reference standard
        assert note_to_freq("A4") == pytest.approx(440.0, abs=1e-4)
        # Middle C (C4)
        assert note_to_freq("C4") == pytest.approx(261.6255, abs=1e-3)
        # Octaves of A
        assert note_to_freq("A3") == pytest.approx(220.0, abs=1e-4)
        assert note_to_freq("A5") == pytest.approx(880.0, abs=1e-4)
        # Accidentals: C#4 vs Db4 enharmonic equivalence
        assert note_to_freq("C#4") == pytest.approx(note_to_freq("Db4"), abs=1e-6)
        assert note_to_freq("F#4") == pytest.approx(note_to_freq("Gb4"), abs=1e-6)
        assert note_to_freq("D#3") == pytest.approx(note_to_freq("Eb3"), abs=1e-6)
        # Unknown note defaults to 440.0 safely
        assert note_to_freq("XYZ9") == 440.0
        assert note_to_freq("") == 440.0

    @pytest.mark.parametrize("mood", ["calm", "tense", "heroic", "playful"])
    def test_every_mood_generates_seamless_16_bar_loop(self, mood, tmp_path):
        out_wav = tmp_path / f"Music_{mood}.wav"
        generate_music_loop(mood, out_wav, sample_rate=44100)
        assert out_wav.is_file()

        with wave.open(str(out_wav), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 44100
            raw = wf.readframes(wf.getnframes())
            data = np.frombuffer(raw, dtype=np.int16) / 32767.0

        analysis = analyze_music_loop(data, sample_rate=44100)
        assert analysis["duration_s"] > 10.0
        assert 0.60 <= analysis["peak"] <= 0.86  # -1.5 dB headroom
        assert analysis["rms"] > 0.05
        assert analysis["seam_ratio"] < 0.20  # Seamless loop boundary (< 2.0 threshold)
        assert analysis["looping_smooth"] is True


class TestAmbienceSynthesis:
    @pytest.mark.parametrize("kind", ["wind", "forest", "dungeon"])
    def test_ambient_beds_seamless_no_silence_dropout(self, kind, tmp_path):
        out_wav = tmp_path / f"Ambience_{kind}.wav"
        generate_ambience_loop(kind, out_wav, duration_s=4.0, sample_rate=44100, seed=42)
        assert out_wav.is_file()

        with wave.open(str(out_wav), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            raw = wf.readframes(wf.getnframes())
            data = np.frombuffer(raw, dtype=np.int16) / 32767.0

        analysis = analyze_ambience_loop(data, sample_rate=44100)
        assert 0.50 <= analysis["peak"] <= 0.85
        assert analysis["rms"] > 0.02
        assert analysis["seam_ratio"] < 1.0  # Smooth circular seam
        assert analysis["looping_smooth"] is True

        # Verify no silence dropouts in the middle of the audio
        window_size = 4410  # 100ms
        energy_windows = [
            np.sqrt(np.mean(data[i:i + window_size] ** 2))
            for i in range(0, len(data) - window_size, window_size)
        ]
        assert all(e > 0.01 for e in energy_windows), "Ambient loop dipped to silence"


class TestSFXPresets:
    def test_list_and_get_sfx_presets(self):
        for style in ["default", "retro", "soft"]:
            presets = list_sfx_presets(style)
            assert len(presets) >= 7
            assert "pickup_chime" in presets
            assert "impact" in presets
            assert "defeat" in presets
            assert "fanfare" in presets
            assert "ui_click" in presets

            for name in presets:
                p = get_sfx_preset(name, style=style)
                assert p is not None
                assert p.preset_id == name
                assert 0.0 < p.gain <= 0.95

    def test_synthesize_with_engine_48khz_resampling(self, tmp_path):
        out_44k = tmp_path / "click_44k.wav"
        out_48k = tmp_path / "click_48k.wav"

        synthesize_sfx_preset("ui_click", out_44k, style="default", sample_rate=44100)
        synthesize_sfx_preset("ui_click", out_48k, style="default", sample_rate=48000)

        with wave.open(str(out_44k)) as w44:
            assert w44.getframerate() == 44100
        with wave.open(str(out_48k)) as w48:
            assert w48.getframerate() == 48000


class TestAudioServiceAndVerification:
    def test_resample_audio(self):
        # Sine wave at 440 Hz
        t = np.linspace(0.0, 1.0, 44100, endpoint=False)
        orig = np.sin(2.0 * np.pi * 440.0 * t)
        resampled = resample_audio(orig, 44100, 48000)
        assert len(resampled) == 48000
        assert np.max(np.abs(resampled)) == pytest.approx(1.0, abs=0.01)

    def test_crossfade_loop(self):
        # Signal with discontinuity at end
        x = np.linspace(0.2, 0.8, 1000)
        x_clean = crossfade_loop(x, crossfade_samples=100)
        assert len(x_clean) == 900
        # Discontinuity between start and end is reduced
        assert abs(x_clean[0] - x_clean[-1]) < abs(x[0] - x[-1])

    def test_verify_audio_loop_helper(self, tmp_path):
        p = tmp_path / "wind.wav"
        generate_ambience_loop("wind", p, duration_s=3.0, sample_rate=44100)
        res = verify_audio_loop(p)
        assert res["loop_seamless"] is True
        assert res["clipped_samples"] == 0
        assert res["peak"] <= 0.95
        assert res["seam_ratio"] < 2.0

    def test_audio_service_full_suite_generation(self, tmp_path):
        dest = tmp_path / "GameAudio"
        ws = tmp_path / "Workspace"
        ws.mkdir(parents=True)
        reg = AssetRegistry(ws)

        svc = AudioService(sample_rate=44100)
        suite = svc.generate_full_suite(dest, mood="heroic", sfx_style="default", ambience_kind="dungeon", registry=reg)

        assert suite["status"] == "PASS"
        assert Path(suite["music"]).is_file()
        assert Path(suite["ambience"]).is_file()
        assert len(suite["sfx"]) >= 7

        # Verify assets registered in registry
        promoted = reg.search(stage="PROMOTE")
        sound_assets = [a for a in promoted if a["asset_type"] == "sound"]
        assert len(sound_assets) >= 9  # 7 SFX + 1 music + 1 ambience
        assert all(a["provenance"] == "PROC" for a in sound_assets)
