"""Systems probe functions and snapshot model (WI-4.2)."""

from __future__ import annotations

import json
import shutil
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import psutil

from .settings import Settings, get_settings


@dataclass(frozen=True)
class SystemRow:
    key: str  # "ollama" | "engine" | "editor" | "ram" | "disk" | "hosted"
    state: str  # "ok" | "degraded" | "offline" | "unknown"
    summary: str  # e.g. "4 models · 7.1 GB VRAM in use"
    fix_action: Optional[str] = None  # "start_ollama" | "set_engine" | "open_hosted" | None


@dataclass(frozen=True)
class SystemsSnapshot:
    rows: Tuple[SystemRow, ...]
    taken_at: float

    @property
    def overall(self) -> str:
        row_dict = {r.key: r.state for r in self.rows}
        if row_dict.get("engine") == "offline" or row_dict.get("ollama") == "offline":
            return "offline"
        if all(r.state == "ok" for r in self.rows):
            return "ok"
        return "degraded"

    def row(self, key: str) -> Optional[SystemRow]:
        for r in self.rows:
            if r.key == key:
                return r
        return None


def probe_ollama(settings: Settings, timeout_s: float = 3.0) -> SystemRow:
    url = getattr(settings, "ollama_url", "http://127.0.0.1:11434")
    try:
        req = urllib.request.Request(f"{url}/api/tags", headers={"User-Agent": "GameForge-IDE"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = data.get("models", [])

        # Check VRAM usage via /api/ps
        vram_bytes = 0
        try:
            req_ps = urllib.request.Request(f"{url}/api/ps", headers={"User-Agent": "GameForge-IDE"})
            with urllib.request.urlopen(req_ps, timeout=timeout_s) as resp_ps:
                ps_data = json.loads(resp_ps.read().decode("utf-8"))
            vram_bytes = sum(m.get("size_vram", 0) for m in ps_data.get("models", []))
        except Exception:
            pass

        vram_gb = vram_bytes / (1024 ** 3)
        if vram_gb > 0:
            summary = f"{len(models)} models · {vram_gb:.1f} GB VRAM in use"
        else:
            summary = f"{len(models)} models"
        return SystemRow(key="ollama", state="ok", summary=summary, fix_action=None)
    except Exception:
        return SystemRow(key="ollama", state="offline", summary="Ollama offline", fix_action="start_ollama")


def probe_engine(settings: Settings) -> SystemRow:
    engine = getattr(settings, "engine", None)
    if engine is not None:
        exe = engine.root / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
        if exe.is_file():
            return SystemRow(key="engine", state="ok", summary=f"UE {engine.version} installed", fix_action=None)
    return SystemRow(key="engine", state="offline", summary="Engine not found", fix_action="set_engine")


def probe_editor() -> SystemRow:
    try:
        from ..backend.tools.game_tools import GameTools
        links = GameTools.all_links() if hasattr(GameTools, "all_links") else getattr(GameTools, "_links", {})
        active = [k for k, v in links.items() if hasattr(v, "is_running") and v.is_running()]
        if active:
            return SystemRow(key="editor", state="ok", summary=f"{len(active)} active editor link{'s' if len(active) != 1 else ''}", fix_action=None)
    except Exception:
        pass
    return SystemRow(key="editor", state="offline", summary="No active editor", fix_action=None)


def probe_ram() -> SystemRow:
    try:
        pct = psutil.virtual_memory().percent
        state = "degraded" if pct > 85.0 else "ok"
        summary = f"{pct:.1f}% used" + (" (> 85%)" if pct > 85.0 else "")
        return SystemRow(key="ram", state=state, summary=summary, fix_action=None)
    except Exception:
        return SystemRow(key="ram", state="unknown", summary="RAM probe error", fix_action=None)


def probe_disk(settings: Settings) -> SystemRow:
    p_root = getattr(settings, "projects_root", None)
    if not p_root or not Path(p_root).exists():
        p_root = Path.cwd()
    try:
        usage = shutil.disk_usage(p_root)
        free_gb = usage.free / (1024 ** 3)
        if free_gb < 20.0:
            return SystemRow(key="disk", state="offline", summary=f"{free_gb:.1f} GB free (< 20 GB)", fix_action=None)
        elif free_gb < 50.0:
            return SystemRow(key="disk", state="degraded", summary=f"{free_gb:.1f} GB free (< 50 GB)", fix_action=None)
        else:
            return SystemRow(key="disk", state="ok", summary=f"{free_gb:.1f} GB free", fix_action=None)
    except Exception:
        return SystemRow(key="disk", state="unknown", summary="Disk probe error", fix_action=None)


def probe_hosted(workspace_root: Optional[Path] = None) -> SystemRow:
    try:
        from ..backend.providers.router import ModelRouter
        router = ModelRouter()
        ws = workspace_root or Path.cwd()
        hosted_map = router.attach_hosted(ws)
        available = [pid for pid, prov in hosted_map.items() if prov.is_available()]
        if available:
            return SystemRow(key="hosted", state="ok", summary=f"{len(available)} profile(s) ready", fix_action=None)
        return SystemRow(key="hosted", state="degraded", summary="No hosted profiles opted in", fix_action="open_hosted")
    except Exception:
        return SystemRow(key="hosted", state="unknown", summary="Not configured", fix_action="open_hosted")


def probe_all(
    settings: Optional[Settings] = None,
    timeout_s: float = 3.0,
    workspace_root: Optional[Path] = None,
) -> SystemsSnapshot:
    s = settings or get_settings()
    rows = (
        probe_ollama(s, timeout_s=timeout_s),
        probe_engine(s),
        probe_editor(),
        probe_ram(),
        probe_disk(s),
        probe_hosted(workspace_root=workspace_root),
    )
    return SystemsSnapshot(rows=rows, taken_at=time.time())
