"""Run the prompt -> playable game pipeline from the command line.

    python scripts/pipeline/run_game_pipeline.py --name TicTacToe [--size 3 --win 3] [--skip-package]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.gameforge_ide.pipeline.game_pipeline import GamePipeline  # noqa: E402
from src.gameforge_ide.recipes.grid_board_game.recipe import GridBoardParams  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="TicTacToe")
    ap.add_argument("--title", default="Tic-Tac-Toe")
    ap.add_argument("--size", type=int, default=3)
    ap.add_argument("--win", type=int, default=3)
    ap.add_argument("--hotseat", action="store_true")
    ap.add_argument("--gravity", action="store_true")
    ap.add_argument("--ai", default="perfect")
    ap.add_argument("--skip-package", action="store_true")
    ap.add_argument("--stop-after", default=None)
    ap.add_argument("--projects-root", default=r"E:\GameForge\projects")
    a = ap.parse_args()
    params = GridBoardParams(project_name=a.name, display_title=a.title, board_size=a.size,
                             win_length=a.win, vs_ai=not a.hotseat, ai_level=a.ai,
                             gravity=a.gravity)
    pipe = GamePipeline(Path(a.projects_root), max_parallel_actions=8,
                        on_event=lambda k, d: print(k, json.dumps(d, default=str)[:300], flush=True))
    res = pipe.run(params, skip_package=a.skip_package, stop_after=a.stop_after)
    print("REPORT", res.report_path, "OK" if res.ok else f"FAILED at {res.failed_stage}")
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
