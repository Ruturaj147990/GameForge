"""Shared engine-demo harness (P0 WI-0.11): disposable probe copies, editor start, report writing.

Paths come from the developer host profile through ``core.settings`` (``probe_project``, ``validation_root``,
``plugin_build``), never from constants in individual demos.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.gameforge_ide.core.settings import get_settings  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402


def _remove_readonly(func: Any, path: str, exc_info: Any) -> None:
    """Clear read-only attribute on Windows before retrying unlink/rmdir."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise


def disposable_probe(tag: str, plugin_build: Optional[Path] = None) -> Path:
    """Copy the probe project to ``<validation_root>/<tag>_<yyyymmdd>`` with the given (or host-profile) plugin build."""
    safe_tag = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in tag).strip("_") or "probe"
    s = get_settings()
    probe_uproject = s.require_dev("probe_project")
    probe = probe_uproject.parent
    dest = s.require_dev("validation_root") / f"{safe_tag}_{time.strftime('%Y%m%d')}"
    if dest.exists():
        shutil.rmtree(dest, onexc=lambda f, p, e: _remove_readonly(f, p, e) if hasattr(shutil, "rmtree") else None)
    shutil.copytree(probe, dest, ignore=shutil.ignore_patterns(
        "DerivedDataCache", "Intermediate", "Saved", "__pycache__", ".gameforge"))
    bins_src = (plugin_build or s.require_dev("plugin_build")) / "Binaries"
    if not bins_src.is_dir():
        raise FileNotFoundError(f"Plugin Binaries directory not found: {bins_src}")
    bins = dest / "Plugins" / "GameForge" / "Binaries"
    if bins.exists():
        shutil.rmtree(bins, onexc=lambda f, p, e: _remove_readonly(f, p, e))
    shutil.copytree(bins_src, bins)
    return dest / probe_uproject.name


def start_editor(uproject: Path, log_name: str, no_sound: bool = True, discovery_timeout_s: int = 900) -> LiveEditorLink:
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=uproject.parent / f"{log_name}.log",
                no_sound=no_sound)
    try:
        link.connect(discovery_timeout_s=discovery_timeout_s)
    except Exception:
        for stopper_name in ("stop", "close", "shutdown"):
            stopper = getattr(link, stopper_name, None)
            if callable(stopper):
                try:
                    stopper()
                except Exception:
                    pass
                break
        raise
    return link


def write_report(name: str, payload: Dict[str, Any], phase: Optional[str] = None) -> Path:
    safe_name = Path(name).name
    safe_phase = Path(phase).name if phase else ""
    out = REPO / "reports" / safe_phase / f"{safe_name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    data.setdefault("finished", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    tmp = out.with_name(f".{out.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return out
