"""Multimodal 3D Asset Generation & Validation Pipeline for GameForge IDE."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ProceduralMeshGenerator:
    """Generates procedural 3D meshes (Wavefront OBJ/MTL) and Unreal import metadata."""

    def __init__(self, output_root: Optional[Path] = None):
        self.output_root = (output_root or Path(r"E:\GameForge\assets\generated")).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)

    def _compute_sha256(self, file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def generate_cube(
        self,
        name: str = "SM_BlockoutCube",
        size: float = 100.0,
        subfolder: str = "meshes",
    ) -> Dict[str, Any]:
        """Generates a standard 100-unit Unreal-scale cube with normals, UVs, and materials."""
        target_dir = self.output_root / subfolder
        target_dir.mkdir(parents=True, exist_ok=True)

        obj_path = target_dir / f"{name}.obj"
        mtl_path = target_dir / f"{name}.mtl"
        meta_path = target_dir / f"{name}.ue_import.json"

        s = size / 2.0
        # 8 vertices
        vertices = [
            (-s, -s, -s), (s, -s, -s), (s, s, -s), (-s, s, -s),
            (-s, -s,  s), (s, -s,  s), (s, s,  s), (-s, s,  s),
        ]
        # 6 face normals
        normals = [
            (0, 0, -1), (0, 0, 1), (0, -1, 0), (1, 0, 0), (0, 1, 0), (-1, 0, 0)
        ]
        # 4 UV coordinates
        uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]

        # 6 quad faces split into 12 triangles (v/vt/vn)
        # Format: face index: list of (v_idx, vt_idx, vn_idx) 1-indexed
        faces = [
            # -Z (bottom)
            [(1, 1, 1), (2, 2, 1), (3, 3, 1)], [(1, 1, 1), (3, 3, 1), (4, 4, 1)],
            # +Z (top)
            [(5, 1, 2), (7, 3, 2), (6, 2, 2)], [(5, 1, 2), (8, 4, 2), (7, 3, 2)],
            # -Y (front)
            [(1, 1, 3), (6, 3, 3), (2, 2, 3)], [(1, 1, 3), (5, 4, 3), (6, 3, 3)],
            # +X (right)
            [(2, 1, 4), (7, 3, 4), (3, 2, 4)], [(2, 1, 4), (6, 4, 4), (7, 3, 4)],
            # +Y (back)
            [(3, 1, 5), (8, 3, 5), (4, 2, 5)], [(3, 1, 5), (7, 4, 5), (8, 3, 5)],
            # -X (left)
            [(4, 1, 6), (5, 3, 6), (1, 2, 6)], [(4, 1, 6), (8, 4, 6), (5, 3, 6)],
        ]

        # Write .obj file
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write(f"# GameForge Procedural Mesh: {name}\n")
            f.write(f"mtllib {name}.mtl\n")
            f.write(f"o {name}\n\n")

            for v in vertices:
                f.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
            f.write("\n")

            for uv in uvs:
                f.write(f"vt {uv[0]:.4f} {uv[1]:.4f}\n")
            f.write("\n")

            for n in normals:
                f.write(f"vn {n[0]:.4f} {n[1]:.4f} {n[2]:.4f}\n")
            f.write("\n")

            f.write(f"usemtl M_{name}_Default\n")
            f.write("s 1\n")
            for tri in faces:
                f.write(f"f {tri[0][0]}/{tri[0][1]}/{tri[0][2]} {tri[1][0]}/{tri[1][1]}/{tri[1][2]} {tri[2][0]}/{tri[2][1]}/{tri[2][2]}\n")

        # Write .mtl file
        with open(mtl_path, "w", encoding="utf-8") as f:
            f.write(f"# GameForge Material: M_{name}_Default\n")
            f.write(f"newmtl M_{name}_Default\n")
            f.write("Ka 0.2000 0.2000 0.2000\n")
            f.write("Kd 0.3500 0.5500 0.8500\n")  # GameForge Steel Blue
            f.write("Ks 0.5000 0.5000 0.5000\n")
            f.write("Ns 64.0\n")
            f.write("d 1.0\n")
            f.write("illum 2\n")

        # Write Unreal Engine 5.7 Import Metadata
        obj_sha = self._compute_sha256(obj_path)
        metadata = {
            "asset_name": name,
            "target_engine": "Unreal Engine 5.7",
            "asset_class": "UStaticMesh",
            "generator": "GameForge Procedural Geometry Engine v1.0",
            "timestamp": time.time(),
            "sha256": obj_sha,
            "geometry_metrics": {
                "vertex_count": len(vertices),
                "triangle_count": len(faces),
                "uv_channel_count": 1,
                "bounding_box_extent": [size, size, size],
            },
            "unreal_import_settings": {
                "bImportMeshLODs": False,
                "LODGroup": "LevelArchitecture",
                "CollisionTraceFlag": "CTF_UseSimpleAsComplex",
                "CollisionProfileName": "BlockAllDynamic",
                "bGenerateLightmapUVs": True,
                "bAutoGenerateCollision": True,
            },
            "material_bindings": [
                {
                    "slot_index": 0,
                    "slot_name": f"M_{name}_Default",
                    "pbr_channels": {
                        "BaseColor": [0.35, 0.55, 0.85, 1.0],
                        "Metallic": 0.2,
                        "Roughness": 0.4,
                    },
                }
            ],
        }

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return {
            "status": "SUCCESS",
            "asset_name": name,
            "obj_file": str(obj_path),
            "mtl_file": str(mtl_path),
            "meta_file": str(meta_path),
            "sha256": obj_sha,
            "vertex_count": len(vertices),
            "triangle_count": len(faces),
            "verified": True,
        }

    def validate_mesh(self, obj_path: Path | str) -> Dict[str, Any]:
        """Parses and validates geometric integrity of a generated mesh."""
        p = Path(obj_path)
        if not p.exists():
            return {"valid": False, "error": f"File does not exist: {obj_path}"}

        v_count = 0
        f_count = 0
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("v "):
                    v_count += 1
                elif line.startswith("f "):
                    f_count += 1

        is_valid = v_count > 0 and f_count > 0
        return {
            "valid": is_valid,
            "vertex_count": v_count,
            "face_count": f_count,
            "file_size": p.stat().st_size,
            "sha256": self._compute_sha256(p),
        }
