"""Roadmap M19: CSV profiler parser."""

import pytest

from src.gameforge_ide.backend.tools.csv_profile import parse_csv_profile


def _write(tmp_path, frames):
    # Real layout (UE 5.7): EVENTS first, mostly empty, with a command event on the last frame.
    lines = ["EVENTS,FrameTime,GameThreadTime,RenderThreadTime,GPUTime"]
    lines += [f",{f},{f * 0.5},{f * 0.6},{f * 0.9}" for f in frames[:-1]]
    lines += [f"Cmd: csvprofile stop,{frames[-1]},{frames[-1] * 0.5},{frames[-1] * 0.6},{frames[-1] * 0.9}"]
    lines += ["EVENTS,FrameTime,GameThreadTime,RenderThreadTime,GPUTime", "[HasHeaderRowAtEnd],1",
              "[platform],Windows,[config],Development"]
    p = tmp_path / "Profile.csv"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_summary_skips_warmup_and_metadata(tmp_path):
    frames = [100.0] * 10 + [16.0] * 90 + [20.0] * 10
    s = parse_csv_profile(_write(tmp_path, frames))
    assert s["frames"] == 100
    assert s["FrameTime"]["mean_ms"] == pytest.approx(16.4, abs=0.01)
    assert s["FrameTime"]["max_ms"] == 20.0 and s["FrameTime"]["p95_ms"] == 20.0
    assert s["GameThreadTime"]["mean_ms"] == pytest.approx(8.2, abs=0.01)
    assert s["avg_fps"] == pytest.approx(61.0, abs=0.1)
    assert "RHIThreadTime" not in s["columns_present"]


def test_empty_file_rejected(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_csv_profile(p)
