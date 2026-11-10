"""Living project level reconciliation and user-edit protection (WI-8.3) plus interrupted run reconciliation."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field

from ..storage.atomic import atomic_write_json
from .model import RunState, StepStatus
from .project_graph import (
    GeneratedBy,
    ProjectGraph,
    ProjectNode,
    compute_actor_state_hash,
)
from .store import _INDEX_LOCK

TAG_GF_OWNED = "GF_Owned"


class ActorConflict(BaseModel):
    actor_id: str
    label: str
    level: str
    recorded_hash: str
    current_hash: str
    current_state: Dict[str, Any] = Field(default_factory=dict)
    planned_state: Dict[str, Any] = Field(default_factory=dict)


class AssetConflict(BaseModel):
    asset_id: str
    path: str
    recorded_sha256: str
    current_sha256: str


class ReconciliationPlan(BaseModel):
    level_id: str
    to_spawn: List[Dict[str, Any]] = Field(default_factory=list)
    to_update: List[Dict[str, Any]] = Field(default_factory=list)
    to_delete: List[str] = Field(default_factory=list)  # labels
    conflicts: List[ActorConflict] = Field(default_factory=list)
    asset_conflicts: List[AssetConflict] = Field(default_factory=list)
    preserved_user_actors: List[str] = Field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts or self.asset_conflicts)


def plan_reconciliation(
    graph: ProjectGraph,
    level_id: str,
    new_plan_actors: List[Dict[str, Any]],
    current_actors: List[Dict[str, Any]],
    resolutions: Optional[Dict[str, Literal["keep_mine", "use_design"]]] = None,
) -> ReconciliationPlan:
    """Compare desired new_plan_actors with current_actors on disk / in engine.

    Returns a ReconciliationPlan detailing spawns, updates, deletes, and conflicts.
    """
    resolutions = resolutions or {}
    plan = ReconciliationPlan(level_id=level_id)

    # 1. Categorise current actors
    owned_current: Dict[str, Dict[str, Any]] = {}
    for a in current_actors:
        if not isinstance(a, dict):
            continue
        label = str(a.get("label") or "")
        if not label:
            continue
        tags = a.get("tags") or []
        if TAG_GF_OWNED in tags:
            owned_current[label] = a
        else:
            plan.preserved_user_actors.append(label)

    # 2. Map planned actors by label (or planned id)
    planned_by_label: Dict[str, Dict[str, Any]] = {}
    for p in new_plan_actors:
        lbl = p.get("label") or p.get("id") or p.get("entity_id")
        if lbl:
            planned_by_label[lbl] = p

    # 3. Check owned current actors: deleted or in plan
    for label, cur_act in owned_current.items():
        node_id = f"{level_id}/{label}"
        node = graph.find_node(node_id)
        cur_hash = compute_actor_state_hash(cur_act)

        if label not in planned_by_label:
            # Actor was owned by GameForge but removed from the new plan
            if node and node.owner == "user":
                # User claimed ownership with "keep_mine"; do not delete
                plan.preserved_user_actors.append(label)
            else:
                plan.to_delete.append(label)
        else:
            # Actor is in both current level and new plan
            planned = planned_by_label[label]
            if node and node.owner == "user":
                # User previously opted to keep their version; ignore planned changes
                plan.preserved_user_actors.append(label)
            elif node and node.state_hash and node.state_hash != cur_hash:
                # State changed outside of Forge! Conflict!
                res = resolutions.get(node_id)
                if res == "keep_mine":
                    # User resolution: convert to user owned, preserve state
                    node.owner = "user"
                    node.state_hash = cur_hash
                    plan.preserved_user_actors.append(label)
                elif res == "use_design":
                    # User resolution: overwrite with design
                    node.owner = "gameforge"
                    node.state_hash = compute_actor_state_hash(planned)
                    plan.to_update.append(planned)
                else:
                    # Unresolved conflict
                    plan.conflicts.append(
                        ActorConflict(
                            actor_id=node_id,
                            label=label,
                            level=level_id,
                            recorded_hash=node.state_hash,
                            current_hash=cur_hash,
                            current_state=cur_act,
                            planned_state=planned,
                        )
                    )
            else:
                # Not user modified; check if planned properties changed
                planned_hash = compute_actor_state_hash(planned)
                if cur_hash != planned_hash:
                    plan.to_update.append(planned)

    # 4. Planned actors not currently present -> spawn
    for label, planned in planned_by_label.items():
        if label not in owned_current:
            plan.to_spawn.append(planned)

    return plan


def apply_resolutions(
    graph: ProjectGraph,
    plan: ReconciliationPlan,
    resolutions: Dict[str, Literal["keep_mine", "use_design"]],
) -> ReconciliationPlan:
    """Apply resolutions to unresolved conflicts in a plan."""
    remaining_conflicts: List[ActorConflict] = []

    for conflict in plan.conflicts:
        node_id = conflict.actor_id
        res = resolutions.get(node_id)
        node = graph.find_node(node_id)
        if not node:
            node = ProjectNode(
                id=node_id,
                kind="actor",
                level=conflict.level,
                label=conflict.label,
                owner="gameforge",
            )
            graph.upsert_node(node)

        if res == "keep_mine":
            node.owner = "user"
            node.state_hash = conflict.current_hash
            plan.preserved_user_actors.append(conflict.label)
        elif res == "use_design":
            node.owner = "gameforge"
            node.state_hash = compute_actor_state_hash(conflict.planned_state)
            plan.to_update.append(conflict.planned_state)
        else:
            remaining_conflicts.append(conflict)

    plan.conflicts = remaining_conflicts
    return plan


def _update_index_file(index_path: Path, reconciled_ids: Dict[str, float]) -> None:
    """Update status and updated_at for reconciled runs in an index JSON file."""
    if not index_path.is_file():
        return
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return

    changed = False
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict) and entry.get("run_id") in reconciled_ids:
                entry["status"] = "INTERRUPTED"
                entry["updated_at"] = reconciled_ids[entry["run_id"]]
                changed = True
    elif isinstance(raw, dict):
        runs_list = raw.get("runs")
        if isinstance(runs_list, list):
            for entry in runs_list:
                if isinstance(entry, dict) and entry.get("run_id") in reconciled_ids:
                    entry["status"] = "INTERRUPTED"
                    entry["updated_at"] = reconciled_ids[entry["run_id"]]
                    changed = True
        for rid, ts in reconciled_ids.items():
            if rid in raw and isinstance(raw[rid], dict):
                raw[rid]["status"] = "INTERRUPTED"
                raw[rid]["updated_at"] = ts
                changed = True

    if changed:
        atomic_write_json(index_path, raw)


def reconcile_interrupted_runs(
    workspace_dir: Union[Path, str],
    project_dir: Optional[Union[Path, str]] = None,
) -> List[str]:
    """Scan persisted Forge runs and mark any orphaned RUNNING runs as INTERRUPTED.

    Also updates `.gameforge/runs/index.json` and `.gameforge/runs_index.json` so
    summary listings never report stale RUNNING status.
    """
    ws = Path(workspace_dir).resolve()
    search_roots: List[Path] = [(ws / ".gameforge" / "runs").resolve()]
    if project_dir is not None:
        proj_runs = (Path(project_dir).resolve() / "Saved" / "GameForge" / "runs").resolve()
        if proj_runs not in search_roots:
            search_roots.append(proj_runs)

    reconciled: Dict[str, float] = {}
    now = time.time()

    with _INDEX_LOCK:
        for runs_root in search_roots:
            if not runs_root.is_dir():
                continue
            for run_dir in sorted(runs_root.iterdir()):
                if not run_dir.is_dir():
                    continue
                state_file = run_dir / "state.json"
                if not state_file.is_file():
                    continue
                try:
                    raw_state = json.loads(state_file.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(raw_state, dict):
                    continue

                status = raw_state.get("status")
                if status in ("RUNNING", "CANCELLING"):
                    raw_state["status"] = "INTERRUPTED"
                    raw_state["updated_at"] = now
                    records = raw_state.get("records")
                    if isinstance(records, dict):
                        for rec in records.values():
                            if isinstance(rec, dict) and rec.get("status") == "RUNNING":
                                rec["status"] = StepStatus.INTERRUPTED.value
                                rec["finished_at"] = now
                                errs = rec.setdefault("errors", [])
                                if isinstance(errs, list):
                                    errs.append("Run interrupted before step completion")
                    atomic_write_json(state_file, raw_state)
                    run_id = (
                        raw_state.get("run", {}).get("run_id")
                        if isinstance(raw_state.get("run"), dict)
                        else None
                    ) or run_dir.name
                    reconciled[str(run_id)] = now

            # Update index files inside or alongside runs_root
            if reconciled:
                _update_index_file(runs_root / "index.json", reconciled)
                _update_index_file(runs_root.parent / "runs_index.json", reconciled)

        if reconciled:
            _update_index_file(ws / ".gameforge" / "runs" / "index.json", reconciled)
            _update_index_file(ws / ".gameforge" / "runs_index.json", reconciled)

    return sorted(reconciled.keys())
