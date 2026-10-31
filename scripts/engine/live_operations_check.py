"""Live check of LiveOperations: quarantine import -> class read-back -> promote -> spawn (UE 5.7.4).

    python scripts/engine/live_operations_check.py <path/to/Probe.uproject>
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.gameforge_ide.backend.tools.asset_tools import ProceduralMeshGenerator  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402
from src.gameforge_ide.unreal.live_operations import LiveOperations  # noqa: E402


async def run(ops: LiveOperations, obj: str) -> dict:
    out = {}
    imp = await ops.import_asset(obj, "/Game/Quarantine/GFCheck", "StaticMesh")
    out["import"] = imp.model_dump()
    if not imp.ok:
        return out
    src = imp.data["primary"]
    prom = await ops.promote_quarantined_asset(src, "/Game/Approved/SM_GFCheck")
    out["promote"] = prom.model_dump()
    spawn = await ops.spawn_actor("StaticMeshActor", {"x": 0, "y": 0, "z": 50}, label="GF_Promoted",
                                  static_mesh="/Game/Approved/SM_GFCheck.SM_GFCheck")
    out["spawn"] = spawn.model_dump()
    out["actor_present"] = any(a["label"] == "GF_Promoted" for a in ops.actors_in_level())
    return out


def main() -> int:
    up = Path(sys.argv[1])
    gen = ProceduralMeshGenerator().generate_cube(name="SM_GFCheck", size=100.0)
    obj = gen.get("obj_file") or next(
        (v for v in gen.values() if isinstance(v, str) and v.endswith(".obj")), None)
    link = LiveEditorLink(up)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"])
    try:
        link.connect(900)
        link.call("new_level", {"level_path": "/Game/Maps/GF_OpsCheck"})
        result = asyncio.run(run(LiveOperations(link), str(obj)))
    finally:
        result_code = link.stop()
    result["editor_exit"] = result_code
    result["ok"] = bool(result.get("import", {}).get("ok") and result.get("promote", {}).get("ok")
                        and result.get("spawn", {}).get("ok") and result.get("actor_present"))
    out = up.parent / "Saved" / "GameForge" / "live_operations_check.json"
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: (v.get("ok") if isinstance(v, dict) else v) for k, v in result.items()}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
