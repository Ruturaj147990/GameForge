"""GameForge Project Graph (WI-8.3).

Tracks ownership, lineage, and state hashes of actors and assets in a living project.
Persisted at <project>/GameForge/project_graph.json (schema project_graph/1).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ..storage.atomic import atomic_write_text
from .model import canonical_hash


class GeneratedBy(BaseModel):
    run_id: str
    step: str
    plan_hash: str


class ProjectNode(BaseModel):
    id: str  # e.g. "level_1/guards_2" or "asset:/Game/GameForge/Materials/MI_floor"
    kind: Literal["actor", "asset"]
    level: Optional[str] = None
    label: Optional[str] = None
    owner: Literal["gameforge", "user"] = "gameforge"
    generated_by: Optional[GeneratedBy] = None
    state_hash: Optional[str] = None
    file_sha256: Optional[str] = None


class ProjectGraph(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: Literal["project_graph/1"] = Field("project_graph/1", alias="schema")
    nodes: List[ProjectNode] = Field(default_factory=list)

    def find_node(self, node_id: str) -> Optional[ProjectNode]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def upsert_node(self, node: ProjectNode) -> None:
        for idx, n in enumerate(self.nodes):
            if n.id == node.id:
                self.nodes[idx] = node
                return
        self.nodes.append(node)

    def remove_node(self, node_id: str) -> bool:
        before = len(self.nodes)
        self.nodes = [n for n in self.nodes if n.id != node_id]
        return len(self.nodes) < before

    @classmethod
    def load(cls, project_dir: Union[Path, str]) -> "ProjectGraph":
        """Load project_graph.json from <project>/GameForge/ or <project>/.gameforge/."""
        pdir = Path(project_dir)
        paths = [
            pdir / "GameForge" / "project_graph.json",
            pdir / ".gameforge" / "project_graph.json",
        ]
        for p in paths:
            if p.is_file():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    return cls.model_validate(data)
                except Exception:
                    pass
        return cls()

    def save(self, project_dir: Union[Path, str]) -> None:
        """Save project_graph.json atomically to both standard locations."""
        pdir = Path(project_dir)
        payload = self.model_dump_json(indent=2, by_alias=True)
        for rel in ["GameForge", ".gameforge"]:
            d = pdir / rel
            d.mkdir(parents=True, exist_ok=True)
            p = d / "project_graph.json"
            atomic_write_text(p, payload, sync=True, backup=False)


def compute_actor_state_hash(actor: Dict[str, Any]) -> str:
    """Compute deterministic canonical hash of an actor's readback transform and properties."""
    payload = {
        "label": actor.get("label", ""),
        "class": actor.get("class", ""),
        "location": actor.get("location", {}),
        "rotation": actor.get("rotation", {}),
        "scale": actor.get("scale", {"x": 1.0, "y": 1.0, "z": 1.0}),
        "properties": actor.get("properties", {}),
    }
    return canonical_hash(payload)


def compute_file_sha256(file_path: Union[Path, str]) -> str:
    """Compute SHA-256 of an asset file on disk."""
    fp = Path(file_path)
    if not fp.is_file():
        return ""
    h = hashlib.sha256()
    try:
        with open(fp, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()
