"""Named, Versioned Unreal Editor Operations Library for GameForge IDE.

Authoritative specification based on GameForge Master Blueprint (Oct 27, 2026):
- Rule 7: Read back after write — every mutation followed by query of resulting state.
- JSON input schema and structured result: ok, data, warnings, errors, affected_paths, reversibility.
- Operations:
  - spawn_actor, import_asset (quarantine), compile_blueprint, set_editor_property.
- Read-back operations:
  - asset_exists, asset_dependencies, actors_in_level, compile_blueprint_result,
    log_tail_since, viewport_screenshot.
- Feature detection against live Unreal 5.7.4 environment.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.gameforge_ide.unreal.op_result import OperationResult
from src.gameforge_ide.unreal.mutation_queue import SerializedMutationQueue
from src.gameforge_ide.unreal.security import UnrealSecurityBoundary
from src.gameforge_ide.unreal.snapshot import SnapshotManager


class UnrealOperationsLibrary:
    """In-memory SIMULATION of the editor operation library for offline tests.

    It never contacts Unreal. Real operations live in GameForge/Content/Python/gameforge_ops.py
    and are reached through live_editor.LiveEditorLink.
    """

    VERSION = "1.0.0"

    def __init__(
        self,
        workspace_root: Path,
        security: Optional[UnrealSecurityBoundary] = None,
        snapshot_mgr: Optional[SnapshotManager] = None,
        mutation_queue: Optional[SerializedMutationQueue] = None,
        engine_root: Optional[Path] = None,
    ):
        self.workspace_root = workspace_root.resolve()
        self.security = security or UnrealSecurityBoundary(self.workspace_root)
        self.snapshots = snapshot_mgr or SnapshotManager(self.workspace_root)
        self.queue = mutation_queue or SerializedMutationQueue()
        self.engine_root = engine_root or Path(r"E:\UE\UE_5.7")
        self._actor_registry: Dict[str, Dict[str, Any]] = {}
        self._asset_registry: Dict[str, Dict[str, Any]] = {}
        self._feature_flags: Dict[str, bool] = self._detect_features()

    def _detect_features(self) -> Dict[str, bool]:
        """Feature-detects Unreal 5.7.4 APIs at initialization."""
        installed = (self.engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe").exists()
        ubt_available = (self.engine_root / "Engine" / "Build" / "BatchFiles" / "Build.bat").exists()
        cmd_available = (self.engine_root / "Engine" / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe").exists()
        return {
            "unreal_5_7_installed": installed,
            "ubt_available": ubt_available,
            "editor_cmd_available": cmd_available,
            "python_remote_execution": True,
            "epic_mcp": False,  # UE 5.8 only, disabled for 5.7.4
            "remote_control_http": False,  # disabled by default
            "interchange_gltf": True,
        }

    def get_supported_operations(self) -> List[str]:
        return [
            "spawn_actor",
            "import_asset",
            "compile_blueprint",
            "set_editor_property",
            "asset_exists",
            "asset_dependencies",
            "actors_in_level",
            "compile_blueprint_result",
            "log_tail_since",
            "viewport_screenshot",
        ]

    # ── Mutation Operations ──────────────────────────────────────────────────

    async def spawn_actor(
        self,
        actor_class: str,
        location: Dict[str, float],
        rotation: Optional[Dict[str, float]] = None,
        label: Optional[str] = None,
        level_path: str = "/Game/Maps/Main",
        token: Optional[str] = None,
    ) -> OperationResult:
        """Spawns an actor inside an editor undo transaction and registers level membership."""
        self.security.authorize_mutation(token, "spawn_actor")

        actor_label = label or f"{actor_class}_{len(self._actor_registry) + 1}"
        affected = [f"{level_path}.umap"]
        snap_id = self.snapshots.create_pre_snapshot("spawn_actor", affected)

        async def _run():
            record = {
                "label": actor_label,
                "class": actor_class,
                "location": location,
                "rotation": rotation or {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                "level": level_path,
                "spawned_at": time.time(),
            }
            self._actor_registry[actor_label] = record
            self.snapshots.commit_post_state(snap_id)
            return {
                "ok": True,
                "actor_label": actor_label,
                "actor_class": actor_class,
                "location": location,
                "level": level_path,
            }

        res = await self.queue.execute_mutation("spawn_actor", _run)
        errs = [res["error"]] if res.get("error") else []
        return OperationResult(
            ok=res.get("ok", False),
            operation="spawn_actor",
            data=res,
            errors=errs,
            affected_paths=affected if res.get("ok") else [],
            reversibility="transactional",
            snapshot_id=snap_id,
        )

    async def import_asset(
        self,
        source_file: str,
        destination_path: str = "/Game/Quarantine/",
        asset_class: str = "StaticMesh",
        token: Optional[str] = None,
    ) -> OperationResult:
        """Imports an asset into quarantine path (/Game/Quarantine/) with snapshot rollback."""
        self.security.authorize_mutation(token, "import_asset")

        src_path = (self.workspace_root / source_file).resolve()
        if not src_path.exists():
            return OperationResult(
                ok=False,
                operation="import_asset",
                errors=[f"Source asset file not found: {source_file}"],
                reversibility="snapshot-only",
            )

        asset_name = src_path.stem
        target_asset_path = f"{destination_path.rstrip('/')}/{asset_name}"
        affected = [f"{target_asset_path}.uasset"]
        snap_id = self.snapshots.create_pre_snapshot("import_asset", affected)

        async def _run():
            self._asset_registry[target_asset_path] = {
                "path": target_asset_path,
                "class": asset_class,
                "source": str(src_path),
                "imported_at": time.time(),
                "dependencies": [],
            }
            self.snapshots.commit_post_state(snap_id)
            return {
                "ok": True,
                "asset_path": target_asset_path,
                "asset_class": asset_class,
                "quarantine": True,
            }

        res = await self.queue.execute_mutation("import_asset", _run)
        errs = [res["error"]] if res.get("error") else []
        return OperationResult(
            ok=res.get("ok", False),
            operation="import_asset",
            data=res,
            errors=errs,
            affected_paths=affected if res.get("ok") else [],
            reversibility="snapshot-only",
            snapshot_id=snap_id,
        )

    async def compile_blueprint(
        self,
        blueprint_path: str,
        token: Optional[str] = None,
    ) -> OperationResult:
        """Compiles a Blueprint asset and records structured compiler diagnostics."""
        self.security.authorize_mutation(token, "compile_blueprint")

        affected = [f"{blueprint_path}.uasset"]
        snap_id = self.snapshots.create_pre_snapshot("compile_blueprint", affected)

        async def _run():
            self.snapshots.commit_post_state(snap_id)
            return {
                "ok": True,
                "blueprint_path": blueprint_path,
                "status": "COMPILED",
                "warnings": [],
                "errors": [],
            }

        res = await self.queue.execute_mutation("compile_blueprint", _run)
        errs = [res["error"]] if res.get("error") else []
        return OperationResult(
            ok=res.get("ok", False),
            operation="compile_blueprint",
            data=res,
            errors=errs,
            affected_paths=affected if res.get("ok") else [],
            reversibility="transactional",
            snapshot_id=snap_id,
        )

    async def set_editor_property(
        self,
        target_label: str,
        property_name: str,
        property_value: Any,
        token: Optional[str] = None,
    ) -> OperationResult:
        """Mutates an actor or asset property via set_editor_property hooks."""
        self.security.authorize_mutation(token, "set_editor_property")

        async def _run():
            if target_label in self._actor_registry:
                self._actor_registry[target_label][property_name] = property_value
                return {"ok": True, "target": target_label, "property": property_name, "value": property_value}
            return {"ok": False, "error": f"Target '{target_label}' not found."}

        res = await self.queue.execute_mutation("set_editor_property", _run)
        errs = [res["error"]] if res.get("error") else []
        return OperationResult(
            ok=res.get("ok", False),
            operation="set_editor_property",
            data=res,
            errors=errs,
            reversibility="transactional",
        )

    async def promote_quarantined_asset(
        self,
        quarantine_path: str,
        approved_path: str,
        token: Optional[str] = None,
    ) -> OperationResult:
        """Promotes an asset from quarantine path to approved project path with AssetTools."""
        self.security.authorize_mutation(token, "promote_asset")

        affected = [f"{quarantine_path}.uasset", f"{approved_path}.uasset"]
        snap_id = self.snapshots.create_pre_snapshot("promote_asset", affected)

        async def _run():
            rec = self._asset_registry.pop(quarantine_path, None)
            if not rec:
                rec = {"path": quarantine_path, "class": "StaticMesh", "dependencies": []}
            rec["path"] = approved_path
            rec["promoted_at"] = time.time()
            rec["quarantine"] = False
            self._asset_registry[approved_path] = rec
            self.snapshots.commit_post_state(snap_id)
            return {
                "ok": True,
                "old_path": quarantine_path,
                "new_path": approved_path,
                "asset_class": rec.get("class", "StaticMesh"),
            }

        res = await self.queue.execute_mutation("promote_asset", _run)
        errs = [res["error"]] if res.get("error") else []
        return OperationResult(
            ok=res.get("ok", False),
            operation="promote_asset",
            data=res,
            errors=errs,
            affected_paths=affected if res.get("ok") else [],
            reversibility="transactional",
            snapshot_id=snap_id,
        )

    # ── Read-Back Operations (Rule 7) ────────────────────────────────────────

    def asset_exists(self, asset_path: str, asset_class: Optional[str] = None) -> Dict[str, Any]:
        """Queries asset existence and validates asset class."""
        rec = self._asset_registry.get(asset_path)
        if rec:
            match = True if not asset_class else (rec.get("class") == asset_class)
            return {"exists": True, "asset_path": asset_path, "class": rec.get("class"), "class_match": match}
        # Check disk fallback
        disk_path = self.workspace_root / f"{asset_path.lstrip('/')}.uasset"
        if disk_path.exists():
            return {"exists": True, "asset_path": asset_path, "class": asset_class or "Unknown", "class_match": True}
        return {"exists": False, "asset_path": asset_path}

    def asset_dependencies(self, asset_path: str) -> Dict[str, Any]:
        """Queries asset dependencies from asset registry."""
        rec = self._asset_registry.get(asset_path, {})
        return {
            "asset_path": asset_path,
            "dependencies": rec.get("dependencies", []),
            "resolved": True,
        }

    def actors_in_level(self, level_path: str = "/Game/Maps/Main") -> List[Dict[str, Any]]:
        """Queries all spawned/placed actors in a specific level."""
        return [
            actor for actor in self._actor_registry.values()
            if actor.get("level") == level_path
        ]

    def compile_blueprint_result(self, blueprint_path: str) -> Dict[str, Any]:
        """Reads back compiler status and error list for a Blueprint."""
        return {
            "blueprint_path": blueprint_path,
            "status": "COMPILED",
            "warnings_count": 0,
            "errors_count": 0,
        }

    def log_tail_since(self, timestamp: float, max_lines: int = 100) -> List[str]:
        """Retrieves recent editor log lines since a timestamp."""
        return [f"[{time.strftime('%H:%M:%S')}] Editor log read-back verified clean."]

    def viewport_screenshot(self, output_path: str) -> Dict[str, Any]:
        """Captures a viewport screenshot for multimodal review."""
        target = (self.workspace_root / output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write minimal valid 1x1 PNG if not present
        if not target.exists():
            # 1x1 transparent PNG bytes
            target.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
        return {
            "ok": True,
            "screenshot_path": str(target),
            "bytes": target.stat().st_size,
        }
