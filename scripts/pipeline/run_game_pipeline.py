"""Run the prompt -> playable game pipeline from the command line.

    python scripts/pipeline/run_game_pipeline.py --prompt "create a tic tac toe game"
    python scripts/pipeline/run_game_pipeline.py --name TicTacToe [--size 3 --win 3] [--skip-package]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.gameforge_ide.core.settings import get_settings  # noqa: E402
from src.gameforge_ide.pipeline.game_pipeline import GamePipeline  # noqa: E402
from src.gameforge_ide.legacy_recipes.grid_board_game.recipe import GridBoardParams  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=None, help="Natural language prompt -> GDS -> game")
    ap.add_argument("--resume", default=None, help="Resume previous Forge run for a project directory")
    ap.add_argument("--name", default="TicTacToe")
    ap.add_argument("--title", default="Tic-Tac-Toe")
    ap.add_argument("--size", type=int, default=3)
    ap.add_argument("--win", type=int, default=3)
    ap.add_argument("--hotseat", action="store_true")
    ap.add_argument("--gravity", action="store_true")
    ap.add_argument("--ai", default="perfect")
    ap.add_argument("--skip-package", action="store_true")
    ap.add_argument("--stop-after", default=None)
    ap.add_argument("--projects-root", default=None, help="Override projects root (defaults to get_settings().projects_root)")
    a = ap.parse_args()

    projects_root = Path(a.projects_root) if a.projects_root else get_settings().projects_root

    if a.resume:
        print(f"Resuming pipeline run for: {a.resume}")
        res = GamePipeline.resume(
            Path(a.resume),
            projects_root=projects_root,
            on_event=lambda k, d: print(k, json.dumps(d, default=str)[:300], flush=True),
        )
        print("REPORT", res.report_path, "OK" if res.ok else f"FAILED at {res.failed_stage}")
        return 0 if res.ok else 1

    if a.prompt:
        from src.gameforge_ide.design.prompt_to_gds import prompt_to_gds
        from src.gameforge_ide.design.legacy import to_legacy_params
        from src.gameforge_ide.design import store as design_store

        print(f"Generating GDS from prompt: {a.prompt!r}")
        gds_res = prompt_to_gds(a.prompt)
        if gds_res.status != "OK" or gds_res.gds is None:
            print(f"FAILED to generate GDS from prompt: {gds_res.status} {gds_res.errors}")
            return 1
        gds = gds_res.gds
        params = to_legacy_params(gds)

        def save_gds_hook(pdir: Path):
            stored = design_store.load(pdir)
            if stored is not None and gds.meta.revision <= stored.meta.revision:
                gds.meta.revision = stored.meta.revision + 1
            design_store.save(pdir, gds)

        pipe = GamePipeline(
            projects_root,
            max_parallel_actions=8,
            on_event=lambda k, d: print(k, json.dumps(d, default=str)[:300], flush=True),
            on_project_dir_ready=save_gds_hook,
        )
    else:
        params = GridBoardParams(
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
            on_event=lambda k, d: print(k, json.dumps(d, default=str)[:300], flush=True),
        )

    res = pipe.run(params, skip_package=a.skip_package, stop_after=a.stop_after)
    print("REPORT", res.report_path, "OK" if res.ok else f"FAILED at {res.failed_stage}")
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
