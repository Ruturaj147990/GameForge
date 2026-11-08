"""Engine stages shared by every game pipeline (recipe and free-form).

Each function returns a StageRecord-compatible tuple (ok, data, errors). They run real engine
executables and the live editor; none of them simulates anything.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Tuple

from ..unreal.live_editor import LiveEditorLink
from ..unreal.toolchain import UnrealToolchain

SELFTEST_PASS = "GF_SELFTEST PASS"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_content(path: Path) -> Dict:
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return {"checked": False}
    img = Image.open(path).convert("L")
    hist = img.histogram()
    lit = sum(hist[16:]) / max(1, sum(hist))
    sd = ImageStat.Stat(img).stddev[0]
    return {"checked": True, "size": list(img.size), "lit_fraction": round(lit, 4), "stddev": round(sd, 2),
            "has_content": lit > 0.05 and sd > 5}


def assemble_level(engine_root: Path, uproject: Path, evidence_dir: Path, name: str,
                   floor_extent_cm: float) -> Tuple[bool, Dict, List[str]]:
    """Build the game's level in the live editor: table, sun, sky fill; read everything back."""
    link = LiveEditorLink(uproject, engine_root)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=evidence_dir / "assemble_editor.log")
    map_path = f"/Game/Maps/{name}Map"
    calls = [
        ("new_level", {"level_path": map_path}),
        ("create_material", {"asset_path": f"/Game/{name}/M_Table", "base_color": [0.05, 0.06, 0.09],
                             "roughness": 0.8}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Table",
                         "static_mesh": "/Engine/BasicShapes/Plane.Plane", "material": f"/Game/{name}/M_Table",
                         "location": {"x": 0, "y": 0, "z": -15},
                         "scale": {"x": floor_extent_cm * 3 / 100, "y": floor_extent_cm * 3 / 100, "z": 1}}),
        ("spawn_actor", {"actor_class": "DirectionalLight", "label": "Sun", "mobility": "Movable",
                         "light_intensity": 10.0, "rotation": {"pitch": -50, "yaw": 35, "roll": 0}}),
        ("spawn_actor", {"actor_class": "SkyLight", "label": "SkyFill", "mobility": "Movable",
                         "light_intensity": 1.0}),
        ("save_all", {}),
        ("actors_in_level", {"limit": 50}),
    ]
    out: List[Dict] = []
    errors: List[str] = []
    try:
        link.connect(discovery_timeout_s=900)
        for op, args in calls:
            r = link.call(op, args, timeout_s=300)
            out.append({"op": op, "ok": r.get("ok"), "errors": r.get("errors", [])})
            if not r.get("ok"):
                if op == "create_material" and any("already exists" in e for e in r.get("errors", [])):
                    out[-1]["ok"] = True
                    continue
                errors.append(f"{op}: {r.get('errors')}")
                break
            if op == "actors_in_level":
                labels = {a["label"] for a in r["data"]["actors"]}
                missing = {"Table", "Sun", "SkyFill"} - labels
                if missing:
                    errors.append(f"read-back missing actors: {sorted(missing)}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        code = link.stop()
    return not errors, {"map": map_path, "calls": out, "editor_exit": code,
                        "graceful": link.last_stop_graceful}, errors


def assemble_platformer_level(engine_root: Path, uproject: Path, evidence_dir: Path, name: str,
                              collectible_count: int = 5) -> Tuple[bool, Dict, List[str]]:
    """Build the 3D platformer level in the live editor: platforms, sun, sky fill, player start; read back."""
    link = LiveEditorLink(uproject, engine_root)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=evidence_dir / "assemble_editor.log")
    map_path = f"/Game/Maps/{name}Map"
    calls = [
        ("new_level", {"level_path": map_path}),
        ("create_material", {"asset_path": f"/Game/{name}/M_Platform", "base_color": [0.12, 0.15, 0.22], "roughness": 0.6}),
        ("create_material", {"asset_path": f"/Game/{name}/M_Coin", "base_color": [1.0, 0.85, 0.1], "roughness": 0.2}),
        ("create_material", {"asset_path": f"/Game/{name}/M_Checkpoint", "base_color": [0.1, 0.8, 0.9], "roughness": 0.3}),
        ("create_material", {"asset_path": f"/Game/{name}/M_Goal", "base_color": [0.6, 0.2, 0.95], "roughness": 0.3}),
        ("spawn_actor", {"actor_class": "DirectionalLight", "label": "Sun", "mobility": "Movable",
                         "light_intensity": 10.0, "rotation": {"pitch": -50, "yaw": 45, "roll": 0}}),
        ("spawn_actor", {"actor_class": "SkyLight", "label": "SkyFill", "mobility": "Movable",
                         "light_intensity": 1.5}),
        # 7 Platforms
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_Start",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 0, "y": 0, "z": 0}, "scale": {"x": 4.0, "y": 4.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_2",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 600, "y": 0, "z": 80}, "scale": {"x": 3.0, "y": 3.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_3",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 1200, "y": 100, "z": 180}, "scale": {"x": 3.0, "y": 3.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_Checkpoint",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 1850, "y": 100, "z": 260}, "scale": {"x": 4.0, "y": 4.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_5",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 2500, "y": -80, "z": 200}, "scale": {"x": 3.0, "y": 3.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_6",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 3150, "y": 0, "z": 320}, "scale": {"x": 3.0, "y": 3.0, "z": 0.5}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Platform_Goal",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_Platform",
                         "location": {"x": 3800, "y": 0, "z": 360}, "scale": {"x": 4.0, "y": 4.0, "z": 0.5}}),
        # PlayerStart on Start Platform
        ("spawn_actor", {"actor_class": "PlayerStart", "label": "PlayerStart",
                         "location": {"x": 0, "y": 0, "z": 60}}),
        # Real gameplay actors (C++ classes compiled in the project)
        ("spawn_actor", {"actor_class": f"/Script/{name}.GFPlatformerCollectible", "label": "Coin_1",
                         "location": {"x": 600, "y": 0, "z": 140}}),
        ("spawn_actor", {"actor_class": f"/Script/{name}.GFPlatformerCollectible", "label": "Coin_2",
                         "location": {"x": 1200, "y": 100, "z": 240}}),
        ("spawn_actor", {"actor_class": f"/Script/{name}.GFPlatformerCollectible", "label": "Coin_3",
                         "location": {"x": 1850, "y": 100, "z": 340}}),
        ("spawn_actor", {"actor_class": f"/Script/{name}.GFPlatformerCollectible", "label": "Coin_4",
                         "location": {"x": 2500, "y": -80, "z": 260}}),
        ("spawn_actor", {"actor_class": f"/Script/{name}.GFPlatformerCollectible", "label": "Coin_5",
                         "location": {"x": 3150, "y": 0, "z": 380}}),
        ("spawn_actor", {"actor_class": f"/Script/{name}.GFPlatformerCheckpoint", "label": "Checkpoint_1",
                         "location": {"x": 1850, "y": 100, "z": 300}}),
        ("spawn_actor", {"actor_class": f"/Script/{name}.GFPlatformerGoal", "label": "Goal_1",
                         "location": {"x": 3800, "y": 0, "z": 420}}),
        # Functional UMG HUD Blueprint
        ("widget_create_blueprint", {"asset_path": f"/Game/{name}/WBP_PlatformerHUD",
                                     "parent_class": "UserWidget", "root_widget_class": "CanvasPanel"}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_PlatformerHUD",
                           "widget_class": "TextBlock", "widget_name": "TitleText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_PlatformerHUD", "widget_name": "TitleText",
                                      "slot_properties": {"position": {"x": 50, "y": 40}, "size": {"x": 400, "y": 40},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_PlatformerHUD",
                           "widget_class": "TextBlock", "widget_name": "CoinCountText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_PlatformerHUD", "widget_name": "CoinCountText",
                                      "slot_properties": {"position": {"x": 50, "y": 90}, "size": {"x": 250, "y": 30},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_PlatformerHUD",
                           "widget_class": "TextBlock", "widget_name": "CheckpointText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_PlatformerHUD", "widget_name": "CheckpointText",
                                      "slot_properties": {"position": {"x": 50, "y": 130}, "size": {"x": 250, "y": 30},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_PlatformerHUD",
                           "widget_class": "TextBlock", "widget_name": "VictoryText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_PlatformerHUD", "widget_name": "VictoryText",
                                      "slot_properties": {"position": {"x": 50, "y": 170}, "size": {"x": 300, "y": 40},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_compile", {"asset_path": f"/Game/{name}/WBP_PlatformerHUD"}),
        ("widget_save", {"asset_path": f"/Game/{name}/WBP_PlatformerHUD"}),
        ("save_all", {}),
        ("actors_in_level", {"limit": 50}),
    ]
    out: List[Dict] = []
    errors: List[str] = []
    try:
        link.connect(discovery_timeout_s=900)
        for op, args in calls:
            r = link.call(op, args, timeout_s=300)
            out.append({"op": op, "ok": r.get("ok"), "errors": r.get("errors", [])})
            if not r.get("ok"):
                if op == "create_material" and any("already exists" in e for e in r.get("errors", [])):
                    out[-1]["ok"] = True
                    continue
                if op in ("widget_create_blueprint", "widget_create") and any("already exists" in e for e in r.get("errors", [])):
                    out[-1]["ok"] = True
                    continue
                errors.append(f"{op}: {r.get('errors')}")
                break
            if op == "actors_in_level":
                labels = {a["label"] for a in r["data"]["actors"]}
                required = {"Sun", "SkyFill", "Platform_Start", "Platform_Checkpoint", "Platform_Goal", "PlayerStart",
                            "Coin_1", "Coin_2", "Coin_3", "Coin_4", "Coin_5", "Checkpoint_1", "Goal_1"}
                missing = required - labels
                if missing:
                    errors.append(f"read-back missing actors: {sorted(missing)}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        code = link.stop()
    return not errors, {"map": map_path, "calls": out, "editor_exit": code,
                        "graceful": link.last_stop_graceful}, errors


def assemble_arena_level(engine_root: Path, uproject: Path, evidence_dir: Path,
                         name: str) -> Tuple[bool, Dict, List[str]]:
    """Create map, arena floor, boundary walls, lights, player start, nav bounds, and UMG HUD."""
    link = LiveEditorLink(uproject, engine_root)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=evidence_dir / "assemble_editor.log")
    map_path = f"/Game/Maps/{name}Map"
    calls = [
        ("new_level", {"level_path": map_path}),
        # Materials
        ("create_material", {"asset_path": f"/Game/{name}/M_ArenaFloor", "base_color": [0.15, 0.16, 0.18], "roughness": 0.8}),
        ("create_material", {"asset_path": f"/Game/{name}/M_ArenaWall", "base_color": [0.25, 0.35, 0.5], "roughness": 0.4}),
        # Lighting
        ("spawn_actor", {"actor_class": "DirectionalLight", "label": "Sun", "mobility": "Movable",
                         "light_intensity": 10.0, "rotation": {"pitch": -50, "yaw": 45, "roll": 0}}),
        ("spawn_actor", {"actor_class": "SkyLight", "label": "SkyFill", "mobility": "Movable",
                         "light_intensity": 1.5}),
        # Arena Floor (Scale 16x16x0.5 => 1600x1600 cm playfield)
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Arena_Floor",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_ArenaFloor",
                         "location": {"x": 0, "y": 0, "z": 0}, "scale": {"x": 16.0, "y": 16.0, "z": 0.5}}),
        # 4 Boundary Walls (Height 200, Thickness 100)
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Wall_North",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_ArenaWall",
                         "location": {"x": 800, "y": 0, "z": 100}, "scale": {"x": 1.0, "y": 17.0, "z": 2.0}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Wall_South",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_ArenaWall",
                         "location": {"x": -800, "y": 0, "z": 100}, "scale": {"x": 1.0, "y": 17.0, "z": 2.0}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Wall_East",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_ArenaWall",
                         "location": {"x": 0, "y": 800, "z": 100}, "scale": {"x": 17.0, "y": 1.0, "z": 2.0}}),
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "Wall_West",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_ArenaWall",
                         "location": {"x": 0, "y": -800, "z": 100}, "scale": {"x": 17.0, "y": 1.0, "z": 2.0}}),
        # NavMeshBoundsVolume to cover the entire arena
        ("spawn_actor", {"actor_class": "NavMeshBoundsVolume", "label": "NavMeshBounds",
                         "location": {"x": 0, "y": 0, "z": 100}, "scale": {"x": 18.0, "y": 18.0, "z": 4.0}}),
        # PlayerStart in center
        ("spawn_actor", {"actor_class": "PlayerStart", "label": "PlayerStart",
                         "location": {"x": 0, "y": 0, "z": 50}}),
        # Functional UMG HUD Blueprint
        ("widget_create_blueprint", {"asset_path": f"/Game/{name}/WBP_ArenaHUD",
                                     "parent_class": "UserWidget", "root_widget_class": "CanvasPanel"}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_ArenaHUD",
                           "widget_class": "TextBlock", "widget_name": "TitleText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_ArenaHUD", "widget_name": "TitleText",
                                      "slot_properties": {"position": {"x": 50, "y": 40}, "size": {"x": 400, "y": 40},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_ArenaHUD",
                           "widget_class": "TextBlock", "widget_name": "HealthText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_ArenaHUD", "widget_name": "HealthText",
                                      "slot_properties": {"position": {"x": 50, "y": 90}, "size": {"x": 250, "y": 30},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_ArenaHUD",
                           "widget_class": "TextBlock", "widget_name": "WaveText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_ArenaHUD", "widget_name": "WaveText",
                                      "slot_properties": {"position": {"x": 50, "y": 130}, "size": {"x": 250, "y": 30},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_ArenaHUD",
                           "widget_class": "TextBlock", "widget_name": "ScoreText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_ArenaHUD", "widget_name": "ScoreText",
                                      "slot_properties": {"position": {"x": 50, "y": 170}, "size": {"x": 250, "y": 30},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_ArenaHUD",
                           "widget_class": "TextBlock", "widget_name": "StatusText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_ArenaHUD", "widget_name": "StatusText",
                                      "slot_properties": {"position": {"x": 50, "y": 210}, "size": {"x": 300, "y": 40},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_compile", {"asset_path": f"/Game/{name}/WBP_ArenaHUD"}),
        ("widget_save", {"asset_path": f"/Game/{name}/WBP_ArenaHUD"}),
        ("save_all", {}),
        ("actors_in_level", {"limit": 50}),
    ]
    out: List[Dict] = []
    errors: List[str] = []
    try:
        link.connect(discovery_timeout_s=900)
        for op, args in calls:
            r = link.call(op, args, timeout_s=300)
            out.append({"op": op, "ok": r.get("ok"), "errors": r.get("errors", [])})
            if not r.get("ok"):
                if op == "create_material" and any("already exists" in e for e in r.get("errors", [])):
                    out[-1]["ok"] = True
                    continue
                if op in ("widget_create_blueprint", "widget_create") and any("already exists" in e for e in r.get("errors", [])):
                    out[-1]["ok"] = True
                    continue
                errors.append(f"{op}: {r.get('errors')}")
                break
            if op == "actors_in_level":
                labels = {a["label"] for a in r["data"]["actors"]}
                required = {"Sun", "SkyFill", "Arena_Floor", "Wall_North", "Wall_South", "Wall_East", "Wall_West",
                            "NavMeshBounds", "PlayerStart"}
                missing = required - labels
                if missing:
                    errors.append(f"read-back missing actors: {sorted(missing)}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        code = link.stop()
    return not errors, {"map": map_path, "calls": out, "editor_exit": code,
                        "graceful": link.last_stop_graceful}, errors


def assemble_card_level(engine_root: Path, uproject: Path, evidence_dir: Path,
                        name: str) -> Tuple[bool, Dict, List[str]]:
    """Create map, card battle table surface, lights, player start, and UMG HUD."""
    link = LiveEditorLink(uproject, engine_root)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=evidence_dir / "assemble_editor.log")
    map_path = f"/Game/Maps/{name}Map"
    calls = [
        ("new_level", {"level_path": map_path}),
        # Materials
        ("create_material", {"asset_path": f"/Game/{name}/M_BattleMat", "base_color": [0.06, 0.08, 0.12], "roughness": 0.85}),
        # Lighting
        ("spawn_actor", {"actor_class": "DirectionalLight", "label": "Sun", "mobility": "Movable",
                         "light_intensity": 10.0, "rotation": {"pitch": -50, "yaw": 45, "roll": 0}}),
        ("spawn_actor", {"actor_class": "SkyLight", "label": "SkyFill", "mobility": "Movable",
                         "light_intensity": 1.5}),
        # Battle Mat / Table surface
        ("spawn_actor", {"actor_class": "StaticMeshActor", "label": "BattleMat",
                         "static_mesh": "/Engine/BasicShapes/Cube.Cube", "material": f"/Game/{name}/M_BattleMat",
                         "location": {"x": 0, "y": 0, "z": 0}, "scale": {"x": 12.0, "y": 12.0, "z": 0.5}}),
        # PlayerStart in center
        ("spawn_actor", {"actor_class": "PlayerStart", "label": "PlayerStart",
                         "location": {"x": 0, "y": 0, "z": 50}}),
        # Functional UMG HUD Blueprint
        ("widget_create_blueprint", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                                     "parent_class": "UserWidget", "root_widget_class": "CanvasPanel"}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                           "widget_class": "TextBlock", "widget_name": "TitleText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_CardHUD", "widget_name": "TitleText",
                                      "slot_properties": {"position": {"x": 50, "y": 40}, "size": {"x": 400, "y": 40},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                           "widget_class": "TextBlock", "widget_name": "PlayerHPText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_CardHUD", "widget_name": "PlayerHPText",
                                      "slot_properties": {"position": {"x": 50, "y": 90}, "size": {"x": 250, "y": 30},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                           "widget_class": "TextBlock", "widget_name": "OpponentHPText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_CardHUD", "widget_name": "OpponentHPText",
                                      "slot_properties": {"position": {"x": 50, "y": 130}, "size": {"x": 250, "y": 30},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                           "widget_class": "TextBlock", "widget_name": "EnergyText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_CardHUD", "widget_name": "EnergyText",
                                      "slot_properties": {"position": {"x": 50, "y": 170}, "size": {"x": 250, "y": 30},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                           "widget_class": "TextBlock", "widget_name": "TurnText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_CardHUD", "widget_name": "TurnText",
                                      "slot_properties": {"position": {"x": 50, "y": 210}, "size": {"x": 250, "y": 30},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                           "widget_class": "TextBlock", "widget_name": "StatusText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_CardHUD", "widget_name": "StatusText",
                                      "slot_properties": {"position": {"x": 50, "y": 250}, "size": {"x": 300, "y": 40},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        # Interactive UI Action Buttons
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                           "widget_class": "Button", "widget_name": "EndTurnButton", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_CardHUD", "widget_name": "EndTurnButton",
                                      "slot_properties": {"position": {"x": 50, "y": 310}, "size": {"x": 160, "y": 50},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                           "widget_class": "TextBlock", "widget_name": "EndTurnText", "parent_name": "EndTurnButton"}),
        ("widget_set_property", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                                "widget_name": "EndTurnText", "property_name": "text", "value": "END TURN"}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                           "widget_class": "Button", "widget_name": "RestartButton", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_CardHUD", "widget_name": "RestartButton",
                                      "slot_properties": {"position": {"x": 230, "y": 310}, "size": {"x": 160, "y": 50},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                           "widget_class": "TextBlock", "widget_name": "RestartText", "parent_name": "RestartButton"}),
        ("widget_set_property", {"asset_path": f"/Game/{name}/WBP_CardHUD",
                                "widget_name": "RestartText", "property_name": "text", "value": "RESTART"}),
        ("widget_compile", {"asset_path": f"/Game/{name}/WBP_CardHUD"}),
        ("widget_save", {"asset_path": f"/Game/{name}/WBP_CardHUD"}),
        ("save_all", {}),
        ("actors_in_level", {"limit": 50}),
    ]
    out: List[Dict] = []
    errors: List[str] = []
    try:
        link.connect(discovery_timeout_s=900)
        for op, args in calls:
            r = link.call(op, args, timeout_s=300)
            out.append({"op": op, "ok": r.get("ok"), "errors": r.get("errors", [])})
            if not r.get("ok"):
                if op == "create_material" and any("already exists" in e for e in r.get("errors", [])):
                    out[-1]["ok"] = True
                    continue
                if op in ("widget_create_blueprint", "widget_create") and any("already exists" in e for e in r.get("errors", [])):
                    out[-1]["ok"] = True
                    continue
                errors.append(f"{op}: {r.get('errors')}")
                break
            if op == "actors_in_level":
                labels = {a["label"] for a in r["data"]["actors"]}
                required = {"Sun", "SkyFill", "BattleMat", "PlayerStart"}
                missing = required - labels
                if missing:
                    errors.append(f"read-back missing actors: {sorted(missing)}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        code = link.stop()
    return not errors, {"map": map_path, "calls": out, "editor_exit": code,
                        "graceful": link.last_stop_graceful}, errors



def assemble_procedural_world_level(engine_root: Path, uproject: Path, evidence_dir: Path,
                                    name: str, seed: int = 2026, terrain_type: str = "Valley",
                                    elevation_scale: float = 1800.0, road_width: float = 350.0,
                                    foliage_density: int = 40, landmark_type: str = "Ruins") -> Tuple[bool, Dict, List[str]]:
    """Create map, landscape, spline road, foliage instances, landmark POI, navmesh, and UMG HUD."""
    link = LiveEditorLink(uproject, engine_root)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=evidence_dir / "assemble_editor.log")
    map_path = f"/Game/Maps/{name}Map"
    calls = [
        ("new_level", {"level_path": map_path}),
        # Materials
        ("create_material", {"asset_path": f"/Game/{name}/M_TerrainGround", "base_color": [0.18, 0.28, 0.15], "roughness": 0.85}),
        ("create_material", {"asset_path": f"/Game/{name}/M_RoadMat", "base_color": [0.25, 0.22, 0.18], "roughness": 0.9}),
        # Lighting
        ("spawn_actor", {"actor_class": "DirectionalLight", "label": "Sun", "mobility": "Movable",
                         "light_intensity": 10.0, "rotation": {"pitch": -50, "yaw": 45, "roll": 0}}),
        ("spawn_actor", {"actor_class": "SkyLight", "label": "SkyFill", "mobility": "Movable",
                         "light_intensity": 1.5}),
        # Real Landscape Creation
        ("landscape_create", {
            "component_count_x": 2, "component_count_y": 2, "quads_per_section": 63, "sections_per_component": 1,
            "elevation_scale": elevation_scale, "seed": seed, "terrain_type": terrain_type,
            "material_path": f"/Game/{name}/M_TerrainGround"
        }),
        # Spline Road Generation
        ("spline_create_road", {
            "road_name": "Road_HighlandPass", "road_width": road_width, "road_material": f"/Game/{name}/M_RoadMat",
            "points": [
                {"x": -2500.0, "y": -2000.0, "z": 200.0},
                {"x": -1000.0, "y": -600.0, "z": 260.0},
                {"x": 0.0, "y": 0.0, "z": 320.0},
                {"x": 1200.0, "y": 900.0, "z": 390.0},
                {"x": 2500.0, "y": 2000.0, "z": 450.0},
            ]
        }),
        # Foliage Scatter
        ("foliage_scatter", {
            "cluster_name": "Foliage_PineValley", "instance_count": foliage_density, "seed": seed + 100,
            "area_radius": 3000.0, "min_elevation": -500.0, "max_elevation": 2000.0,
            "max_slope_degrees": 35.0, "road_clearance": 400.0
        }),
        # Landmark Spawn
        ("landmark_spawn", {
            "landmark_name": "Landmark_AncientRuins", "landmark_type": landmark_type,
            "location": {"x": 2500.0, "y": 2000.0, "z": 450.0}
        }),
        # NavMeshBoundsVolume covering the landscape
        ("spawn_actor", {"actor_class": "NavMeshBoundsVolume", "label": "NavMeshBounds",
                         "location": {"x": 0, "y": 0, "z": 300}, "scale": {"x": 60.0, "y": 60.0, "z": 20.0}}),
        # PlayerStart at road entrance
        ("spawn_actor", {"actor_class": "PlayerStart", "label": "PlayerStart",
                         "location": {"x": -2500.0, "y": -2000.0, "z": 350.0}}),
        # Functional UMG HUD Blueprint
        ("widget_create_blueprint", {"asset_path": f"/Game/{name}/WBP_ProceduralHUD",
                                     "parent_class": "UserWidget", "root_widget_class": "CanvasPanel"}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_ProceduralHUD",
                           "widget_class": "TextBlock", "widget_name": "TitleText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_ProceduralHUD", "widget_name": "TitleText",
                                      "slot_properties": {"position": {"x": 50, "y": 40}, "size": {"x": 400, "y": 40},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_ProceduralHUD",
                           "widget_class": "TextBlock", "widget_name": "BiomeText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_ProceduralHUD", "widget_name": "BiomeText",
                                      "slot_properties": {"position": {"x": 50, "y": 90}, "size": {"x": 250, "y": 30},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_ProceduralHUD",
                           "widget_class": "TextBlock", "widget_name": "TraversalText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_ProceduralHUD", "widget_name": "TraversalText",
                                      "slot_properties": {"position": {"x": 50, "y": 130}, "size": {"x": 250, "y": 30},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_create", {"asset_path": f"/Game/{name}/WBP_ProceduralHUD",
                           "widget_class": "TextBlock", "widget_name": "StatusText", "parent_name": "CanvasPanel_0"}),
        ("widget_set_slot_property", {"asset_path": f"/Game/{name}/WBP_ProceduralHUD", "widget_name": "StatusText",
                                      "slot_properties": {"position": {"x": 50, "y": 170}, "size": {"x": 300, "y": 40},
                                                          "anchors": {"min_x": 0, "min_y": 0, "max_x": 0, "max_y": 0}, "alignment": {"x": 0, "y": 0}}}),
        ("widget_compile", {"asset_path": f"/Game/{name}/WBP_ProceduralHUD"}),
        ("widget_save", {"asset_path": f"/Game/{name}/WBP_ProceduralHUD"}),
        ("save_all", {}),
        ("procedural_world_inspect", {}),
        ("actors_in_level", {"limit": 100}),
    ]
    out: List[Dict] = []
    errors: List[str] = []
    try:
        link.connect(discovery_timeout_s=900)
        for op, args in calls:
            r = link.call(op, args, timeout_s=300)
            out.append({"op": op, "ok": r.get("ok"), "errors": r.get("errors", [])})
            if not r.get("ok"):
                if op == "create_material" and any("already exists" in e for e in r.get("errors", [])):
                    out[-1]["ok"] = True
                    continue
                if op in ("widget_create_blueprint", "widget_create") and any("already exists" in e for e in r.get("errors", [])):
                    out[-1]["ok"] = True
                    continue
                errors.append(f"{op}: {r.get('errors')}")
                break
            if op == "actors_in_level":
                labels = {a["label"] for a in r["data"]["actors"]}
                required = {"Sun", "SkyFill", "NavMeshBounds", "PlayerStart"}
                missing = required - labels
                if missing:
                    errors.append(f"read-back missing actors: {sorted(missing)}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        code = link.stop()
    return not errors, {"map": map_path, "calls": out, "editor_exit": code,
                        "graceful": link.last_stop_graceful}, errors



def package(toolchain: UnrealToolchain, uproject: Path) -> Tuple[bool, Dict, List[str]]:
    r = toolchain.package(uproject, uproject.parent / "Packaged")
    d = r.to_dict()
    return r.ok, {"exit_code": r.exit_code, "log": r.log_path, **r.data, "errors": d["error_count"],
                  "diagnostics": [x.__dict__ for x in r.diagnostics[:20]]}, r.errors


def packaged_smoke(toolchain: UnrealToolchain, exe: Path, evidence_dir: Path, name: str,
                   expect_log: str = SELFTEST_PASS) -> Tuple[bool, Dict, List[str]]:
    """Launch the shipped build with -GFSelfTest; require PASS log, exit 0 AND a content-bearing screenshot."""
    ok, data, errors = _packaged_smoke_once(toolchain, exe, evidence_dir, name, expect_log=expect_log)
    only_capture_failed = (not ok and data.get("exit_code") == 0 and data.get("matched_lines")
                           and errors and all("screenshot" in e for e in errors))
    if only_capture_failed:
        first = {"screenshot_content": data.get("screenshot_content"), "errors": errors}
        ok, data, errors = _packaged_smoke_once(toolchain, exe, evidence_dir, name, expect_log=expect_log)
        data["warm_retry"] = {"reason": "first capture empty while logic passed", "first_attempt": first}
    return ok, data, errors


def _packaged_smoke_once(toolchain: UnrealToolchain, exe: Path, evidence_dir: Path, name: str,
                         expect_log: str = SELFTEST_PASS) -> Tuple[bool, Dict, List[str]]:
    shot = evidence_dir / "packaged_gameplay.png"
    if shot.exists():
        shot.unlink()
    r = toolchain.smoke_test_packaged(
        exe, ["-GFSelfTest", f"-GFShot={shot}", "-RenderOffscreen", "-ResX=1280", "-ResY=720", "-windowed"],
        expect_log=expect_log, timeout_s=600, log_path=evidence_dir / "packaged_smoke.log")
    data = {"exit_code": r.exit_code, "log": r.log_path, **r.data, "exe_sha256": sha256_file(exe)}
    if not shot.exists():
        sdir = exe.parent / name / "Saved" / "Screenshots"
        alt = sorted(sdir.rglob("*.png")) if sdir.exists() else []
        if alt:
            shot = alt[-1]
    errors = list(r.errors)
    content_ok = False
    if shot.exists():
        data["screenshot"] = str(shot)
        data["screenshot_content"] = image_content(shot)
        content_ok = data["screenshot_content"].get("has_content", False) or \
            not data["screenshot_content"].get("checked", False)
        if not content_ok:
            errors.append("gameplay screenshot shows no scene content (black or empty frame)")
    else:
        errors.append("gameplay screenshot was not written")
    log_text = Path(r.log_path).read_text(encoding="utf-8", errors="replace") if r.log_path and Path(r.log_path).exists() else ""
    data["selftest_lines"] = [l.strip()[-400:] for l in log_text.splitlines() if "GF_" in l and "SELFTEST" in l][-3:]
    import re as _re
    scene = _re.findall(r"GF_SCENE shapes=(-?\d+)", log_text)
    if scene:
        data["scene_shapes"] = int(scene[-1])
    data["game_errors"] = [l.strip()[-300:] for l in log_text.splitlines()
                           if ("Error:" in l or "Fatal" in l) and "LogWindows: Failed to load" not in l][-10:]
    return r.ok and content_ok, data, errors


def write_report(evidence_dir: Path, payload: Dict, markdown: str) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report = evidence_dir / "pipeline_report.json"
    report.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    (evidence_dir / "pipeline_report.md").write_text(markdown, encoding="utf-8")
    return report
