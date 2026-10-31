"""Shared engine-demo harness (P0 WI-0.11): disposable probe copies, editor start, report writing.

Paths come from the developer host profile through ``core.settings`` (``probe_project``, ``validation_root``,
``plugin_build``), never from constants in individual demos.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.gameforge_ide.core.settings import get_settings  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402


def disposable_probe(tag: str, plugin_build: Optional[Path] = None) -> Path:
    """Copy the probe project to ``<validation_root>/<tag>_<yyyymmdd>`` with the given (or host-profile) plugin build."""
    s = get_settings()
    probe = s.require_dev("probe_project").parent
    dest = s.require_dev("validation_root") / f"{tag}_{time.strftime('%Y%m%d')}"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(probe, dest, ignore=shutil.ignore_patterns(
        "DerivedDataCache", "Intermediate", "Saved", "__pycache__", ".gameforge"))
    bins = dest / "Plugins" / "GameForge" / "Binaries"
    if bins.exists():
        shutil.rmtree(bins)
    shutil.copytree((plugin_build or s.require_dev("plugin_build")) / "Binaries", bins)
    return dest / "GFProbe.uproject"


def start_editor(uproject: Path, log_name: str, no_sound: bool = True) -> LiveEditorLink:
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=uproject.parent / f"{log_name}.log",
                no_sound=no_sound)
    link.connect(discovery_timeout_s=900)
    return link


def write_report(name: str, payload: dict, phase: Optional[str] = None) -> Path:
    out = REPO / "reports" / (phase or "") / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload.setdefault("finished", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return out
