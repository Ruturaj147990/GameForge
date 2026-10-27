"""Run the free-form (no recipe) game pipeline.

    python scripts/run_freeform_game.py --prompt "create a whack-a-mole game" [--reference]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.gameforge_ide.pipeline.freeform import FreeformGamePipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--title", default=None)
    ap.add_argument("--reference", action="store_true", help="use the built-in reference impl (framework check)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--resume", action="store_true", help="keep existing model-written files; continue from the build")
    ap.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--projects-root", default=r"E:\GameForge\projects")
    a = ap.parse_args()
    pipe = FreeformGamePipeline(Path(a.workspace), Path(a.projects_root), use_reference_impl=a.reference,
                                local_model=a.model, resume=a.resume,
                                on_event=lambda k, d: print(k, json.dumps(d, default=str)[:260], flush=True))
    res = pipe.run(a.prompt, a.title)
    print("REPORT", res["report_path"], res["status"], res.get("failed_stage") or "")
    return 0 if res["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
