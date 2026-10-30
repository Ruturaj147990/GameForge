"""Audit 2026-10-30: rebuild the four playable recipes end to end on the real UE 5.7.4 toolchain.

Builds into new project names (Audit*) so earlier generated projects stay intact. Every stage
is real: scaffold, UBT build, live-editor level assembly, in-engine automation tests,
BuildCookRun packaging and the packaged self-test with screenshot gate.

    python scripts/audit_rebuild_games.py [platformer arena cards world]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.gameforge_ide.pipeline.game_pipeline import GamePipeline  # noqa: E402
from src.gameforge_ide.recipes.arena_combat.recipe import ArenaCombatParams  # noqa: E402
from src.gameforge_ide.recipes.card_battler.recipe import CardBattlerParams  # noqa: E402
from src.gameforge_ide.recipes.platformer.recipe import PlatformerParams  # noqa: E402
from src.gameforge_ide.recipes.procedural_world.recipe import ProceduralWorldParams  # noqa: E402

GAMES = {
    "platformer": lambda: PlatformerParams(project_name="AuditPlatformer", display_title="Audit Platformer"),
    "arena": lambda: ArenaCombatParams(project_name="AuditArena", display_title="Audit Arena"),
    "cards": lambda: CardBattlerParams(project_name="AuditCards", display_title="Audit Cards"),
    "world": lambda: ProceduralWorldParams(project_name="AuditWorld", display_title="Audit World"),
}
SUMMARY = ROOT / "reports" / "audit_20261030_pipeline_runs.json"


def main(argv) -> int:
    wanted = argv or list(GAMES)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.is_file() else {}
    all_ok = True
    for key in wanted:
        params = GAMES[key]()
        print(f"=== {key}: {params.project_name} ===", flush=True)
        t0 = time.time()
        res = GamePipeline().run(params)
        stages = [{"stage": s.stage, "ok": s.ok, "duration_s": round(s.duration_s, 1), "errors": s.errors[:5]}
                  for s in res.stages]
        for s in stages:
            print(f"  [{'OK' if s['ok'] else 'FAIL'}] {s['stage']} {s['duration_s']}s {s['errors'] or ''}", flush=True)
        summary[key] = {
            "project": params.project_name, "ok": res.ok, "failed_stage": res.failed_stage,
            "duration_s": round(time.time() - t0, 1), "stages": stages,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        all_ok &= bool(res.ok)
    print("ALL_OK" if all_ok else "SOME_FAILED", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
