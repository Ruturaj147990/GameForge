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

    # ── Blueprint Graph Operations ─────────────────────────────────────────
    async def blueprint_inspect(self, blueprint_path: str) -> OperationResult:
        return await self._call("blueprint_inspect", {"blueprint_path": blueprint_path}, "read-only")

    async def blueprint_readback_graph(self, blueprint_path: str, graph_name: str = "EventGraph") -> OperationResult:
        return await self._call("blueprint_readback_graph", {"blueprint_path": blueprint_path, "graph_name": graph_name}, "read-only")

    async def blueprint_create_node(self, blueprint_path: str, node_type: str, pos_x: int = 0, pos_y: int = 0,
                                    graph_name: str = "EventGraph", extra_params: Optional[Dict[str, Any]] = None) -> OperationResult:
        args = {"blueprint_path": blueprint_path, "node_type": node_type, "pos_x": pos_x, "pos_y": pos_y,
                "graph_name": graph_name, "extra_params": extra_params or {}}
        return await self._call("blueprint_create_node", args, "transactional")

    async def blueprint_set_pin_default(self, blueprint_path: str, node_id: str, pin_name: str,
                                        default_value: str) -> OperationResult:
        args = {"blueprint_path": blueprint_path, "node_id": node_id, "pin_name": pin_name, "default_value": default_value}
        return await self._call("blueprint_set_pin_default", args, "transactional")

    async def blueprint_connect_pins(self, blueprint_path: str, from_node: str, from_pin: str,
                                     to_node: str, to_pin: str) -> OperationResult:
        args = {"blueprint_path": blueprint_path, "from_node": from_node, "from_pin": from_pin,
                "to_node": to_node, "to_pin": to_pin}
        return await self._call("blueprint_connect_pins", args, "transactional")

    async def blueprint_disconnect_pins(self, blueprint_path: str, from_node: str, from_pin: str,
                                        to_node: str = "", to_pin: str = "") -> OperationResult:
        args = {"blueprint_path": blueprint_path, "from_node": from_node, "from_pin": from_pin,
                "to_node": to_node, "to_pin": to_pin}
        return await self._call("blueprint_disconnect_pins", args, "transactional")

    async def blueprint_delete_node(self, blueprint_path: str, node_id: str) -> OperationResult:
        return await self._call("blueprint_delete_node", {"blueprint_path": blueprint_path, "node_id": node_id}, "transactional")

    async def blueprint_compile(self, blueprint_path: str) -> OperationResult:
        return await self._call("blueprint_compile", {"blueprint_path": blueprint_path}, "transactional")

    async def blueprint_save(self, blueprint_path: str) -> OperationResult:
        return await self._call("blueprint_save", {"blueprint_path": blueprint_path}, "snapshot-only")

    async def pie_start(self, wait_s: float = 1.0) -> OperationResult:
        return await self._call("pie_start", {"wait_s": wait_s}, "transient")

    async def pie_stop(self) -> OperationResult:
        return await self._call("pie_stop", {}, "transient")

    # ── UMG Widget Operations ───────────────────────────────────────────────

    async def widget_create_blueprint(self, asset_path: str, parent_class: str = "UserWidget",
                                      root_widget_class: str = "CanvasPanel") -> OperationResult:
        args = {"asset_path": asset_path, "parent_class": parent_class, "root_widget_class": root_widget_class}
        return await self._call("widget_create_blueprint", args, "transactional")

    async def widget_inspect(self, asset_path: str) -> OperationResult:
        return await self._call("widget_inspect", {"asset_path": asset_path}, "read-only")

    async def widget_readback_tree(self, asset_path: str) -> OperationResult:
        return await self._call("widget_readback_tree", {"asset_path": asset_path}, "read-only")

    async def widget_create(self, asset_path: str, widget_class: str, widget_name: str,
                            parent_name: str = "") -> OperationResult:
        args = {"asset_path": asset_path, "widget_class": widget_class, "widget_name": widget_name, "parent_name": parent_name}
        return await self._call("widget_create", args, "transactional")

    async def widget_set_property(self, asset_path: str, widget_name: str, property_name: str,
                                  value: Any) -> OperationResult:
        args = {"asset_path": asset_path, "widget_name": widget_name, "property_name": property_name, "value": value}
        return await self._call("widget_set_property", args, "transactional")

    async def widget_set_slot_property(self, asset_path: str, widget_name: str,
                                       slot_properties: Dict[str, Any]) -> OperationResult:
        args = {"asset_path": asset_path, "widget_name": widget_name, "slot_properties": slot_properties}
        return await self._call("widget_set_slot_property", args, "transactional")

    async def widget_remove(self, asset_path: str, widget_name: str) -> OperationResult:
        return await self._call("widget_remove", {"asset_path": asset_path, "widget_name": widget_name}, "transactional")

    async def widget_compile(self, asset_path: str) -> OperationResult:
        return await self._call("widget_compile", {"asset_path": asset_path}, "transactional")

    async def widget_save(self, asset_path: str) -> OperationResult:
        return await self._call("widget_save", {"asset_path": asset_path}, "snapshot-only")

    async def widget_display_in_game(self, asset_path: str, z_order: int = 0) -> OperationResult:
        return await self._call("widget_display_in_game", {"asset_path": asset_path, "z_order": z_order}, "transient")

    async def widget_bind_event(self, asset_path: str, widget_name: str, delegate_name: str = "OnClicked",
                                action_type: str = "PrintString", action_params: Optional[Dict[str, Any]] = None) -> OperationResult:
        args = {"asset_path": asset_path, "widget_name": widget_name, "delegate_name": delegate_name,
                "action_type": action_type, "action_params": action_params or {}}
        return await self._call("widget_bind_event", args, "snapshot-only")

    async def widget_inspect_events(self, asset_path: str) -> OperationResult:
        return await self._call("widget_inspect_events", {"asset_path": asset_path}, "read-only")

    async def widget_click_button(self, button_name: str, asset_path: str = "") -> OperationResult:
        return await self._call("widget_click_button", {"button_name": button_name, "asset_path": asset_path}, "transient")

    async def widget_runtime_state(self, asset_path: str) -> OperationResult:
        return await self._call("widget_runtime_state", {"asset_path": asset_path}, "read-only")

    async def gameplay_get_state(self) -> OperationResult:
        return await self._call("gameplay_get_state", {}, "read-only")

    async def gameplay_modify_state(self, delta_health: float = 0.0, delta_stamina: float = 0.0,
                                    menu_action: str = "") -> OperationResult:
        args = {"delta_health": delta_health, "delta_stamina": delta_stamina, "menu_action": menu_action}
        return await self._call("gameplay_modify_state", args, "transient")

