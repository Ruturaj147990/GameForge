"""Real editor-operation backend for QuarantinePipeline and LevelLayoutGenerator.

Same interface the old simulated library offered, but every call goes to the live editor through
LiveEditorLink and returns the editor's own read-back. Blocking link calls run in a worker thread so
async callers are never stalled.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from .live_editor import LiveEditorLink
from .op_result import OperationResult
from .security import UnrealSecurityBoundary


class LiveOperations:
    def __init__(self, link: LiveEditorLink, workspace_root: Optional[Path] = None):
        self.link = link
        # QuarantinePipeline reads a session token from here; the editor checks its own token file.
        self.security = UnrealSecurityBoundary(Path(workspace_root or link.project_dir))

    async def _call(self, op: str, args: Dict[str, Any], reversibility: str) -> OperationResult:
        res = await asyncio.to_thread(self.link.call, op, args)
        return OperationResult(ok=bool(res.get("ok")), operation=op, data=res.get("data") or {},
                               warnings=res.get("warnings") or [], errors=res.get("errors") or [],
                               affected_paths=res.get("affected_paths") or [],
                               reversibility=res.get("reversibility", reversibility))

    async def spawn_actor(self, actor_class: str, location: Dict[str, float], rotation: Optional[Dict] = None,
                          label: Optional[str] = None, level_path: str = "", token: Optional[str] = None,
                          **extra: Any) -> OperationResult:
        args = {"actor_class": actor_class, "location": location, "rotation": rotation or {}, "label": label, **extra}
        return await self._call("spawn_actor", args, "transactional")

    async def import_asset(self, source_file: str, destination_path: str = "/Game/Quarantine",
                           asset_class: str = "StaticMesh", token: Optional[str] = None) -> OperationResult:
        res = await self._call("import_asset", {"source_file": str(source_file),
                                                "destination_path": destination_path}, "snapshot-only")
        if res.ok:
            # An import yields the requested asset plus companions (materials, textures); at least one
            # imported asset must read back as the requested class.
            primary = None
            for path in res.data.get("verified", []):
                check = await self._call("asset_exists", {"asset_path": path.split(".")[0],
                                                          "asset_class": asset_class}, "read-only")
                if check.data.get("class_match"):
                    primary = path.split(".")[0]
                    break
            res.data["primary"] = primary
            res.data["companions"] = [p.split(".")[0] for p in res.data.get("verified", []) if p.split(".")[0] != primary]
            if primary is None:
                res.ok = False
                res.errors.append(f"read-back: no imported asset is a {asset_class}")
        return res

    async def promote_quarantined_asset(self, quarantine_path: str, approved_path: str,
                                        token: Optional[str] = None) -> OperationResult:
        return await self._call("rename_asset", {"source_path": quarantine_path, "destination_path": approved_path},
                                "snapshot-only")

    def actors_in_level(self, level_path: str = "") -> List[Dict[str, Any]]:
        res = self.link.call("actors_in_level", {"limit": 5000})
        return (res.get("data") or {}).get("actors", []) if res.get("ok") else []
