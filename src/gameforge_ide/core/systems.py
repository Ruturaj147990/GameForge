"""Systems probe functions and snapshot model (WI-4.2)."""

from __future__ import annotations

import json
import shutil
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

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
        # Core local operational dependencies
        core_keys = {"ollama", "engine", "ram", "disk"}
        core_states = [r.state for r in self.rows if r.key in core_keys]
        if any(s == "offline" for s in core_states):
            return "offline"
        if any(s in ("degraded", "unknown") for s in core_states):
            return "degraded"
        # If all core services are ok, system is overall ok (hosted is optional opt-in)
        return "ok"

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
            vram_bytes = sum(((m.get("size_vram") or 0) if isinstance(m, dict) else 0) for m in ps_data.get("models", []))
        except Exception:
            pass

        # Check Ollama version and compare against evaluation report
        version_changed = False
        try:
            req_ver = urllib.request.Request(f"{url}/api/version", headers={"User-Agent": "GameForge-IDE"})
            with urllib.request.urlopen(req_ver, timeout=timeout_s) as resp_ver:
                ver_data = json.loads(resp_ver.read().decode("utf-8"))
            live_ver = ver_data.get("version")
            if live_ver:
                # Check latest eval report in reports/P9 relative to repo or cwd
                candidate_rep_dirs = [
                    Path(__file__).resolve().parents[2] / "reports" / "P9",
                    Path("reports/P9"),
                ]
                for rep_dir in candidate_rep_dirs:
                    if rep_dir.is_dir():
                        for rep_file in rep_dir.glob("eval_*.json"):
                            try:
                                rep_data = json.loads(rep_file.read_text(encoding="utf-8"))
                                rep_ver = rep_data.get("version_info")
                                if rep_ver and rep_ver != "unknown" and rep_ver != live_ver:
                                    version_changed = True
                                    break
                            except Exception:
                                pass
                        if version_changed:
                            break
        except Exception:
            pass

        vram_gb = vram_bytes / (1024 ** 3)
        if len(models) == 0:
            return SystemRow(
                key="ollama",
                state="degraded",
                summary="0 models installed (pull model in Settings)",
                fix_action="pull_models",
            )

        if vram_gb > 0:
            summary = f"{len(models)} models · {vram_gb:.1f} GB VRAM in use"
        else:
            summary = f"{len(models)} models"

        if version_changed:
            summary += " · Models changed since last evaluation"

        return SystemRow(key="ollama", state="ok", summary=summary, fix_action=None)
    except Exception:
        return SystemRow(key="ollama", state="offline", summary="Ollama offline", fix_action="start_ollama")


def probe_engine(settings: Settings) -> SystemRow:
    engine = getattr(settings, "engine", None)
    if engine is not None:
        try:
            exe = engine.root / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
            if exe.is_file():
                return SystemRow(key="engine", state="ok", summary=f"UE {engine.version} installed", fix_action=None)
        except Exception:
            pass
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
        if psutil is None:
            return SystemRow(key="ram", state="unknown", summary="psutil not installed", fix_action=None)
        vm = psutil.virtual_memory()
        pct = vm.percent
        used_gb = (vm.total - vm.available) / (1024 ** 3)
        total_gb = vm.total / (1024 ** 3)
        state = "degraded" if pct > 85.0 else "ok"
        summary = f"{used_gb:.1f}/{total_gb:.1f} GB ({pct:.0f}% used)" + (" (> 85%)" if pct > 85.0 else "")
        return SystemRow(key="ram", state=state, summary=summary, fix_action=None)
    except Exception:
        return SystemRow(key="ram", state="unknown", summary="RAM probe error", fix_action=None)


def probe_disk(settings: Settings) -> SystemRow:
    p_root: Optional[Path] = None
    try:
        configured = getattr(settings, "projects_root", None)
        if configured:
            p_cand = Path(configured)
            if p_cand.is_dir():
                p_root = p_cand
            elif p_cand.anchor and Path(p_cand.anchor).is_dir():
                p_root = Path(p_cand.anchor)
    except Exception:
        pass
    if p_root is None:
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
