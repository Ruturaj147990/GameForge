"""Run the prompt -> playable game pipeline from the command line.

    python scripts/pipeline/run_game_pipeline.py --prompt "create a tic tac toe game"
    python scripts/pipeline/run_game_pipeline.py --name TicTacToe [--size 3 --win 3] [--skip-package]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, Optional, Union

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.design.gds import GameDesignSpec
from src.gameforge_ide.legacy_recipes.grid_board_game.recipe import GridBoardParams
from src.gameforge_ide.pipeline.game_pipeline import GamePipeline


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


def format_event_payload(data: Dict[str, Any], verbose: bool) -> str:
    """Format pipeline event payload cleanly with bounded width."""
    payload_str = json.dumps(data, default=str)
    if not verbose and len(payload_str) > 260:
        return payload_str[:257] + "..."
    return payload_str


def main() -> int:
    ap = argparse.ArgumentParser(description="Run prompt-to-game synthesis and build pipeline")
    ap.add_argument("--prompt", default=None, help="Natural language prompt -> GDS -> game")
    ap.add_argument("--resume", default=None, help="Resume previous Forge run for a project directory")
    ap.add_argument("--name", default="TicTacToe", help="Default project name for parameter-driven board game")
    ap.add_argument("--title", default="Tic-Tac-Toe", help="Display title for parameter-driven board game")
    ap.add_argument("--size", type=int, default=3, help="Grid board size (default: 3)")
    ap.add_argument("--win", type=int, default=3, help="Grid board win streak length (default: 3)")
    ap.add_argument("--hotseat", action="store_true", help="Enable two-player local hotseat mode")
    ap.add_argument("--gravity", action="store_true", help="Enable Connect-Four style column gravity")
    ap.add_argument("--ai", default="perfect", help="AI difficulty level ('easy', 'medium', 'perfect')")
    ap.add_argument("--skip-package", action="store_true", help="Skip final standalone packaging stage")
    ap.add_argument("--stop-after", default=None, help="Stop execution after completing the specified stage")
    ap.add_argument("--projects-root", default=None, help="Override projects root (defaults to settings)")
    ap.add_argument("--verbose", action="store_true", help="Enable verbose event payload output")
    a = ap.parse_args()

    projects_root = resolve_projects_root(Path(a.projects_root) if a.projects_root else None)
    projects_root.mkdir(parents=True, exist_ok=True)

    t_start = time.monotonic()

    def on_pipeline_event(kind: str, data: Dict[str, Any]) -> None:
        print(f"[{kind}] {format_event_payload(data, a.verbose)}", flush=True)

    if a.resume:
        resume_path = Path(a.resume).resolve()
        print(f"Resuming pipeline run for: {resume_path}")
        res = GamePipeline.resume(
            resume_path,
            projects_root=projects_root,
            on_event=on_pipeline_event,
        )
        elapsed = round(time.monotonic() - t_start, 2)
        print(f"REPORT: path={res.report_path} status={'OK' if res.ok else 'FAILED'} failed_stage={res.failed_stage or 'none'} elapsed={elapsed}s")
        return 0 if res.ok else 1

    params_or_gds: Union[GameDesignSpec, GridBoardParams]

    if a.prompt:
        from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds
        from src.gameforge_ide.design import store as design_store
        from src.gameforge_ide.design.legacy import to_legacy_params, LegacyUnsupported

        print(f"Generating GDS from prompt: {a.prompt!r}")
        gds_res = prompt_to_gds(a.prompt)
        if gds_res.status != "OK" or gds_res.gds is None:
            print(f"FAILED to generate GDS from prompt: {gds_res.status} {gds_res.errors}", file=sys.stderr)
            return 1

        gds = gds_res.gds
        # Prefer modern GameDesignSpec directly; fall back to legacy params only if strictly compatible
        try:
            params_or_gds = to_legacy_params(gds)
        except (LegacyUnsupported, Exception):
            params_or_gds = gds

        def save_gds_hook(pdir: Path) -> None:
            stored = design_store.load(pdir)
            if stored is not None and gds.meta.revision <= stored.meta.revision:
                gds.meta.revision = stored.meta.revision + 1
            design_store.save(pdir, gds)

        pipe = GamePipeline(
            projects_root,
            max_parallel_actions=8,
            on_event=on_pipeline_event,
            on_project_dir_ready=save_gds_hook,
        )
    else:
        params_or_gds = GridBoardParams(
            project_name=a.name,
            display_title=a.title,
            board_size=a.size,
            win_length=a.win,
            vs_ai=not a.hotseat,
            ai_level=a.ai,
            gravity=a.gravity,
        )
        pipe = GamePipeline(
            projects_root,
            max_parallel_actions=8,
            on_event=on_pipeline_event,
        )

    try:
        res = pipe.run(params_or_gds, skip_package=a.skip_package, stop_after=a.stop_after)
        elapsed = round(time.monotonic() - t_start, 2)
        print(f"REPORT: path={res.report_path} status={'OK' if res.ok else 'FAILED'} failed_stage={res.failed_stage or 'none'} elapsed={elapsed}s")
        return 0 if res.ok else 1
    except Exception as exc:
        elapsed = round(time.monotonic() - t_start, 2)
        print(f"Pipeline run FAILED with exception after {elapsed}s: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
