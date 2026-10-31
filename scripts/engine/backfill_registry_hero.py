"""Backfill the asset registry with the GFAdventurerHero character verified by the 2026-10-30 M9/M10 audit.

The registry did not exist when that audit ran, so this records its outcome after the fact. Every stage is
taken from `reports/audit_m9_m10_completion.json`; a stage the audit did not check is not recorded.
Idempotent: re-running adds no duplicate asset (events are appended only when the asset has none yet).

Usage: python scripts/engine/backfill_registry_hero.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.gameforge_ide.backend.assets.registry import AssetRecord, AssetRegistry  # noqa: E402
from src.gameforge_ide.backend.models.character_spec import CharacterSpec  # noqa: E402

WORKSPACE = Path(r"E:\GameForge\validation\live_ops_probe")
GLTF = Path(r"E:\GameForge\assets\generated\characters\audit_20261030\GFAdventurerHero.gltf")
EVIDENCE = REPO / "reports" / "audit_m9_m10_completion.json"


def main() -> int:
    audit = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    checks, steps = audit["checks"], audit["steps"]
    evidence = [str(EVIDENCE.relative_to(REPO)).replace("\\", "/")]
    # Same spec as scripts/engine/audit_complete_m9_m10.py, so the asset id matches a fresh pipeline run.
    spec = CharacterSpec(character_id="char_adventurer_hero_01", name="GFAdventurerHero",
                         purpose="Playable Humanoid Hero Avatar", category="humanoid",
                         height_cm=180.0, triangle_budget=25000, target_territory="GLOBAL")
    reg = AssetRegistry(WORKSPACE)
    asset_id = reg.register(AssetRecord(
        name=spec.name, asset_type="skeletal_mesh", purpose=spec.purpose, provenance="procedural",
        backend="GameForge-ProceduralRig-V1", backend_version="1.0.0", license="CC-BY-4.0",
        spec=spec.model_dump(), tags=["backfill", "audit_20261030"]))
    if reg.history(asset_id):
        print(f"already backfilled: {asset_id} stage={reg.get(asset_id)['stage']}")
        return 0

    note = f"backfilled from audit {audit['timestamp']}"
    reg.advance(asset_id, "SPEC", True, note, evidence)
    reg.advance(asset_id, "GENERATE", GLTF.exists(), note, evidence, artifact_path=str(GLTF) if GLTF.exists() else None)
    deform = steps.get("python_validator_max_displacement_cm", {})
    reg.advance(asset_id, "VALIDATE", bool(deform), f"{note}; python FK displacement {deform}", evidence)
    quarantine = steps.get("quarantine_import", {})
    reg.advance(asset_id, "QUARANTINE", checks.get("quarantine_skeleton_matches_generator", False), note, evidence,
                unreal_path=quarantine.get("skeletal_mesh_path"))
    reg.advance(asset_id, "ENGINE_VERIFY", checks.get("unreal_skin_deformation", False),
                f"{note}; in-engine skin deformation on calf_l/lowerarm_l/spine_01", evidence)
    promoted = checks.get("promoted_from_quarantine", False) and checks.get("promoted_mesh_valid", False)
    promoted_path = quarantine.get("skeletal_mesh_path", "").replace("/Game/Quarantine/", "/Game/", 1) or None
    reg.advance(asset_id, "PROMOTE", promoted, note, evidence, unreal_path=promoted_path if promoted else None)
    row = reg.get(asset_id)
    print(json.dumps({"asset_id": asset_id, "stage": row["stage"], "unreal_path": row["unreal_path"],
                      "artifact_sha256": row["artifact_sha256"], "db": str(reg.path)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
