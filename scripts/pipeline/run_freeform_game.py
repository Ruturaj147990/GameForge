"""Run the free-form (no recipe) game pipeline.

    python scripts/pipeline/run_freeform_game.py --prompt "create a space shooter" [--reference]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.pipeline.freeform import FreeformGamePipeline


def unload_ollama_model(model_id: str, host: str = "127.0.0.1:11434") -> bool:
    """Explicitly release model from GPU VRAM via Ollama API keep_alive=0."""
    try:
        url = f"http://{host}/api/generate"
        payload = json.dumps({"model": model_id, "keep_alive": 0}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception:
        return False


def resolve_projects_root(override: Optional[Path] = None) -> Path:
    """Resolve projects root from override, settings, or safe fallback."""
    if override:
        return override
    try:
        settings = get_settings()
        if settings.projects_root:
            p = Path(settings.projects_root)
            if p.parent.exists():
                return p
    except Exception:
        pass
    cand = Path(r"E:\GameForge\projects")
    if cand.parent.exists():
        return cand
    return REPO_ROOT / "scratch" / "projects"


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the free-form game pipeline")
    ap.add_argument("--prompt", required=True, help="Natural language prompt describing the game")
    ap.add_argument("--title", default=None, help="Explicit game project title override")
    ap.add_argument("--reference", action="store_true", help="Use the built-in reference impl (framework check)")
    ap.add_argument("--model", default=None, help="Local Ollama model ID to query")
    ap.add_argument("--resume", action="store_true", help="Keep existing model-written files; continue from the build")
    ap.add_argument("--workspace", default=str(REPO_ROOT), help="Workspace root directory")
    ap.add_argument("--projects-root", default=None, help="Projects root directory")
    ap.add_argument("--verbose", action="store_true", help="Enable verbose event payload logging")
    a = ap.parse_args()

    ws_dir = Path(a.workspace).resolve()
    p_root = resolve_projects_root(Path(a.projects_root) if a.projects_root else None)
    p_root.mkdir(parents=True, exist_ok=True)

    def on_pipeline_event(kind: str, data: Dict[str, Any]) -> None:
        payload_str = json.dumps(data, default=str)
        if not a.verbose and len(payload_str) > 260:
            payload_str = payload_str[:257] + "..."
        print(f"[{kind}] {payload_str}", flush=True)

    try:
        pipe = FreeformGamePipeline(
            workspace_root=ws_dir,
            projects_root=p_root,
            use_reference_impl=a.reference,
            local_model=a.model,
            resume=a.resume,
            on_event=on_pipeline_event,
        )
        res = pipe.run(a.prompt, a.title)
        status = res.get("status", "FAILED")
        report_path = res.get("report_path", "none")
        failed_stage = res.get("failed_stage") or ""
        print(f"REPORT: path={report_path} status={status} failed_stage={failed_stage}")
        return 0 if status == "SUCCESS" else 1
    except Exception as exc:
        print(f"Freeform pipeline run FAILED with error: {exc}", file=sys.stderr)
        return 1
    finally:
        if a.model:
            unloaded = unload_ollama_model(a.model)
            if unloaded:
                print(f"Cleaned up Ollama model {a.model} from VRAM.")


if __name__ == "__main__":
    raise SystemExit(main())
