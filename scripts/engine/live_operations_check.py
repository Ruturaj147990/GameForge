"""Live check of LiveOperations: quarantine import -> class read-back -> promote -> spawn (UE 5.7.4).

    python scripts/engine/live_operations_check.py <path/to/Probe.uproject>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.gameforge_ide.backend.tools.asset_tools import ProceduralMeshGenerator  # noqa: E402
from src.gameforge_ide.core.settings import get_settings  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402
from src.gameforge_ide.unreal.live_operations import LiveOperations  # noqa: E402


def _get_probe_project() -> Path:
    try:
        val_root = get_settings().require_dev("validation_root")
        probe = Path(val_root) / "Probe" / "Probe.uproject"
        if probe.exists():
            return probe
    except Exception:
        pass
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "scratch" / "Probe" / "Probe.uproject"


async def run(ops: LiveOperations, obj: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    imp = await ops.import_asset(obj, "/Game/Quarantine/GFCheck", "StaticMesh")
    out["import"] = imp.model_dump()
    if not imp.ok or not imp.data:
        return out
    src = imp.data.get("primary", "")
    if not src:
        out["error"] = "No primary asset produced by import"
        return out
    prom = await ops.promote_quarantined_asset(src, "/Game/Approved/SM_GFCheck")
    out["promote"] = prom.model_dump()
    spawn = await ops.spawn_actor(
        "StaticMeshActor",
        {"x": 0, "y": 0, "z": 50},
        label="GF_Promoted",
        static_mesh="/Game/Approved/SM_GFCheck.SM_GFCheck",
    )
    out["spawn"] = spawn.model_dump()
    actors = ops.actors_in_level()
    out["actor_present"] = any(a.get("label") == "GF_Promoted" for a in actors if isinstance(a, dict))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Live operations check against Unreal Engine")
    parser.add_argument("uproject", nargs="?", default=None, help="Path to .uproject file")
    args = parser.parse_args()

    if args.uproject:
        up = Path(args.uproject).resolve()
    else:
        up = _get_probe_project()

    gen = ProceduralMeshGenerator().generate_cube(name="SM_GFCheck", size=100.0)
    obj = gen.get("obj_file") or next(
        (v for v in gen.values() if isinstance(v, str) and v.endswith(".obj")), None
    )
    link = LiveEditorLink(up)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"])
    result: Dict[str, Any] = {}
    result_code = -1
    try:
        link.connect(900)
        link.call("new_level", {"level_path": "/Game/Maps/GF_OpsCheck"})
        result = asyncio.run(run(LiveOperations(link), str(obj)))
    except Exception as exc:
        result["fatal"] = f"{type(exc).__name__}: {exc}"
    finally:
        result_code = link.stop()

    result["editor_exit"] = result_code
    result["ok"] = bool(
        (result.get("import") or {}).get("ok")
        and (result.get("promote") or {}).get("ok")
        and (result.get("spawn") or {}).get("ok")
        and result.get("actor_present")
    )
    out = up.parent / "Saved" / "GameForge" / "live_operations_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    tmp.replace(out)
    print(json.dumps({k: (v.get("ok") if isinstance(v, dict) else v) for k, v in result.items()}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
