"""Composer data models (WI-6.1).

Defines the core data contracts for game composition: OpCall, PlacedActor,
LevelPlan, CodegenTask, Composition, and CompositionError.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field


class OpCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: str                                  # must be in op_catalog.agent_ops(); args validated by op_schemas (strict)
    args: Dict[str, Any] = Field(default_factory=dict)
    expect: Dict[str, Any] = Field(default_factory=dict)              # e.g. {"ok": True, "data.count": 3}
    purpose: str = ""                        # human-readable line for the Build log


class PlacedActor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str                            # "<entity_id>_<n>" (unique, stable across rebuilds for the same GDS)
    entity_id: Optional[str] = None          # None for geometry/props owned by the layout
    runtime_class: str
    location: Tuple[float, float, float]     # centimetres, level space
    yaw: float = 0.0
    tags: List[str] = Field(default_factory=list)                     # always includes GF_E_<entity_id> and GF_Owned
    properties: Dict[str, Any] = Field(default_factory=dict)          # UPROPERTY name -> value


class LevelPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level_id: str
    map_path: str                            # /Game/Maps/<LevelId>
    partitioned: bool = False
    player_start: Tuple[float, float, float]
    nav_bounds: Tuple[Tuple[float, float, float], Tuple[float, float, float]]   # center, extent (cm)
    geometry_ops: List[OpCall] = Field(default_factory=list)               # floors, walls, platforms
    actors: List[PlacedActor] = Field(default_factory=list)
    lighting: Literal["day", "dusk", "night", "indoor"] = "day"
    nav_checks: List[Tuple[str, str]] = Field(default_factory=list)        # (from actor_id | "player_start", to actor_id)


class CodegenTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handler_name: str                        # "Custom0Rule"
    description: str
    rule_id: str


class Composition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gds_id: str
    gds_revision: int
    project_name: str
    modules: List[str]                       # kit module ids used
    plugins: List[str]                       # .uproject plugins to enable
    module_deps: List[str]                   # Build.cs deps for the game module
    levels: List[LevelPlan]
    gfdef: Dict[str, Any]                    # gfdef/1
    codegen: List[CodegenTask] = Field(default_factory=list)
    scenarios: List[str] = Field(default_factory=list)                     # scenario ids to generate
    content_requests: List[Dict[str, Any]] = Field(default_factory=list)   # VFX/SFX preset requests
    warnings: List[str] = Field(default_factory=list)


class CompositionError(Exception):
    """Raised when GDS cannot be composed into a playable game."""
    def __init__(self, problems: List[str], suggestions: Optional[List[str]] = None):
        self.problems = problems
        self.suggestions = suggestions or []
        msg = f"Composition failed with {len(problems)} problem(s):\n" + "\n".join(f"  - {p}" for p in problems)
        if self.suggestions:
            msg += "\nSuggestions:\n" + "\n".join(f"  * {s}" for s in self.suggestions)
        super().__init__(msg)
