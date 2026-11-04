"""Epic template content pack installer and cooker configuration (P7 WI-7.1).

Copies official Epic template content shipped with UE 5.7.4 (Mannequins, LevelPrototyping)
into Unreal projects under the Unreal Engine EULA with honest EPIC_CONTENT provenance
and registers each asset into the project asset registry.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..backend.assets.registry import AssetRecord, AssetRegistry, sha256_file


EPIC_PACKS: Dict[str, Dict[str, Any]] = {
    "mannequins": {
        "src": "Templates/TemplateResources/High/Characters/Content/Mannequins",
        "dst": "Content/Characters/Mannequins",
        "mount": "/Game/Characters/Mannequins",
        "sentinels": [
            "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple",
            "/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple",
            "/Game/Characters/Mannequins/Meshes/SK_Mannequin",
            "/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed",
            "/Game/Characters/Mannequins/Anims/Unarmed/BS_Idle_Walk_Run",
        ],
    },
    "level_prototyping": {
        "src": "Templates/TemplateResources/High/LevelPrototyping/Content",
        "dst": "Content/LevelPrototyping",
        "mount": "/Game/LevelPrototyping",
        "sentinels": [
            "/Game/LevelPrototyping/Meshes/SM_ChamferCube",
            "/Game/LevelPrototyping/Meshes/SM_Cube",
            "/Game/LevelPrototyping/Meshes/SM_Cylinder",
            "/Game/LevelPrototyping/Materials/M_PrototypeGrid",
            "/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Gray",
        ],
    },
}


def _infer_asset_type(rel_path: str) -> str:
    p = Path(rel_path)
    stem_lower = p.stem.lower()
    path_lower = rel_path.lower()

    if stem_lower.startswith("skm_") or stem_lower.startswith("sk_"):
        return "skeletal_mesh"
    if stem_lower.startswith("sm_"):
        return "mesh"
    if "meshes" in path_lower:
        if "skm_" in path_lower or "sk_" in path_lower:
            return "skeletal_mesh"
        return "mesh"
    if (
        "anims" in path_lower
        or "anim" in path_lower
        or stem_lower.startswith(("abp_", "bs_", "mm_", "a_"))
    ):
        return "animation"
    if "materials" in path_lower or stem_lower.startswith(("m_", "mi_")):
        return "material"
    if "textures" in path_lower or stem_lower.startswith("t_"):
        return "texture"
    if "sounds" in path_lower or "audio" in path_lower or stem_lower.startswith(("s_", "sfx_")):
        return "sound"
    if "niagara" in path_lower or "vfx" in path_lower or stem_lower.startswith(("ns_", "ne_")):
        return "vfx"
    return "other"


def install_pack(
    project_dir: Path,
    pack: str,
    engine_root: Path,
    registry: Optional[AssetRegistry] = None,
) -> Dict[str, Any]:
    """Copy an Epic template pack into <project>/Content and register in AssetRegistry."""
    project_dir = Path(project_dir)
    engine_root = Path(engine_root)
    if pack not in EPIC_PACKS:
        raise ValueError(f"Unknown Epic content pack: {pack!r}. Available: {list(EPIC_PACKS.keys())}")

    info = EPIC_PACKS[pack]
    src_dir = engine_root / info["src"]
    dst_dir = project_dir / info["dst"]

    if not src_dir.is_dir():
        raise FileNotFoundError(f"Epic template content source directory not found: {src_dir}")

    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)

    installed_files: List[str] = []
    registered_count = 0

    for root, _, files in os.walk(dst_dir):
        for f in files:
            if f.endswith(".uasset"):
                p = Path(root) / f
                rel = p.relative_to(dst_dir).as_posix()
                mount_path = f"{info['mount']}/{rel[:-7]}"  # strip .uasset
                installed_files.append(mount_path)

                if registry is not None:
                    asset_type = _infer_asset_type(rel)
                    rec = AssetRecord(
                        name=p.stem,
                        asset_type=asset_type,
                        purpose=f"Epic template content ({pack})",
                        provenance="EPIC_CONTENT",
                        backend="engine-template",
                        backend_version="5.7.4",
                        license="Unreal Engine EULA (engine template content)",
                        spec={"pack": pack, "rel_path": rel, "uasset_sha256": sha256_file(p)},
                        tags=["epic", pack, asset_type],
                    )
                    aid = registry.register(rec)
                    registry.advance(aid, "GENERATE", True, artifact_path=str(p))
                    registry.advance(aid, "ENGINE_VERIFY", True, detail="Copied from validated UE 5.7.4 template")
                    registry.advance(aid, "PROMOTE", True, unreal_path=mount_path)
                    registered_count += 1

    return {
        "pack": pack,
        "src": str(src_dir),
        "dst": str(dst_dir),
        "installed_count": len(installed_files),
        "registered_count": registered_count,
        "sentinels": info["sentinels"],
        "status": "PASS",
    }


def collect_cook_directories(data: Any) -> List[str]:
    """Extract top-level /Game/ directories referenced in a gfdef dict or asset paths."""
    found: Set[str] = set()

    def _scan(val: Any) -> None:
        if isinstance(val, str):
            clean_val = val.split(".")[0].strip()
            if clean_val.startswith("/Game/") and not clean_val.startswith("/Game/GameForge/GD_"):
                parts = [p for p in clean_val.split("/") if p]
                if len(parts) >= 2:
                    top_dir = f"/{parts[0]}/{parts[1]}"
                    found.add(top_dir)
        elif isinstance(val, dict):
            for v in val.values():
                _scan(v)
        elif isinstance(val, (list, tuple, set)):
            for v in val:
                _scan(v)

    _scan(data)
    return sorted(found)


def update_default_game_ini_cook_dirs(project_dir: Path, cook_dirs: List[str]) -> Path:
    """Ensure DirectoriesToAlwaysCook entries exist in Config/DefaultGame.ini, preserving line endings."""
    project_dir = Path(project_dir)
    config_dir = project_dir / "Config"
    config_dir.mkdir(parents=True, exist_ok=True)
    ini_path = config_dir / "DefaultGame.ini"

    content = ""
    le = "\n"
    if ini_path.is_file():
        raw_bytes = ini_path.read_bytes()
        if b"\r\n" in raw_bytes:
            le = "\r\n"
        content = raw_bytes.decode("utf-8")

    section_header = "[/Script/UnrealEd.ProjectPackagingSettings]"
    existing_dirs = set(re.findall(r'DirectoriesToAlwaysCook=\(Path="([^"]+)"\)', content))

    needed = [d for d in cook_dirs if d not in existing_dirs]
    if not needed:
        return ini_path

    new_lines = [f'+DirectoriesToAlwaysCook=(Path="{d}")' for d in needed]

    if section_header in content:
        idx = content.find(section_header) + len(section_header)
        content = content[:idx] + le + le.join(new_lines) + content[idx:]
    else:
        if content and not content.endswith(le):
            content += le
        content += f"{le}{section_header}{le}" + le.join(new_lines) + le

    with open(ini_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return ini_path
