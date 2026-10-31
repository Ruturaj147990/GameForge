"""Parser for Unreal CSV profiler captures (roadmap M19).

`csvprofile start` / `csvprofile stop` write `Saved/Profiling/CSV/Profile(<timestamp>).csv`: a header row of stat
names (first column EVENTS), one row per frame, then trailing metadata rows ("[HasHeaderRowAtEnd]", ...). This reads the
per-frame timing columns and summarises them.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

TIMING_COLUMNS = ("FrameTime", "GameThreadTime", "RenderThreadTime", "GPUTime", "RHIThreadTime")


def parse_csv_profile(path: str | Path, skip_frames: int = 10) -> dict:
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise ValueError("empty CSV profile")
    header = rows[0]
    index = {name: i for i, name in enumerate(header)}
    frames = []
    for row in rows[1:]:
        # The first column is EVENTS: usually empty, sometimes an event name such as "Cmd: csvprofile stop".
        if not row or row[0].startswith("[") or row == header or len(row) < len(header) // 2:
            continue
        try:
            float(row[index.get("FrameTime", 0)])
        except (ValueError, IndexError):
            continue  # metadata / header-at-end rows
        frames.append(row)
    frames = frames[skip_frames:] if len(frames) > skip_frames * 2 else frames
    summary = {"frames": len(frames), "columns_present": [c for c in TIMING_COLUMNS if c in index]}
    for col in TIMING_COLUMNS:
        if col not in index:
            continue
        values = []
        for row in frames:
            try:
                values.append(float(row[index[col]]))
            except (ValueError, IndexError):
                pass
        if values:
            ordered = sorted(values)
            summary[col] = {"mean_ms": round(statistics.fmean(values), 3),
                            "p95_ms": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 3),
                            "max_ms": round(ordered[-1], 3)}
    if "FrameTime" in summary:
        summary["avg_fps"] = round(1000.0 / summary["FrameTime"]["mean_ms"], 1) if summary["FrameTime"]["mean_ms"] else None
    return summary
