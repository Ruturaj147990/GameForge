"""Argument models for editor ops (AD-14), validated host-side before anything reaches the editor.

Hand-reviewed models below take precedence over the generated drafts in ``op_schemas_generated.py``
(``scripts/tools/gen_op_schemas.py``). In P0 an op without any schema passes through unchanged unless
``strict=True``; P2 makes strict validation the default for the agent gateway and the composer.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .op_schemas_generated import GENERATED


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Vec3(_Strict):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class Rot3(_Strict):
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


Label = Field(min_length=1, max_length=200)
GamePath = Field(pattern=r"^/(Game|Engine|Script)/")


class SpawnActorArgs(_Strict):
    label: Optional[str] = Field(None, min_length=1, max_length=200)
    actor_class: str = "StaticMeshActor"
    static_mesh: Optional[str] = None
    location: Vec3 = Field(default_factory=Vec3)
    rotation: Rot3 = Field(default_factory=Rot3)
    scale: Optional[Vec3] = None
    mobility: Optional[str] = None
    material: Optional[str] = None
    light_intensity: Optional[float] = None   # read only for light actors


class NewLevelArgs(_Strict):
    level_path: str = GamePath
    partitioned: bool = False
    if_exists: str = "load"


class LoadLevelArgs(_Strict):
    level_path: str = GamePath


class SetActorPropertyArgs(_Strict):
    label: str = Label
    property: str = Field(min_length=1, max_length=120)
    value: Any
    asset: bool = False  # value is an asset path to load


class DeleteActorArgs(_Strict):
    label: str = Label


class ActorsInLevelArgs(_Strict):
    limit: int = Field(1000, ge=1, le=100000)


REVIEWED: dict[str, type[BaseModel]] = {
    "spawn_actor": SpawnActorArgs,
    "new_level": NewLevelArgs,
    "load_level": LoadLevelArgs,
    "set_actor_property": SetActorPropertyArgs,
    "delete_actor": DeleteActorArgs,
    "actors_in_level": ActorsInLevelArgs,
}

SCHEMAS: dict[str, type[BaseModel]] = {**GENERATED, **REVIEWED}


def validate_args(op: str, args: dict, strict: bool = False) -> tuple[Optional[dict], list[str]]:
    """Return (clean_args, errors). ``clean_args`` is None when validation failed."""
    model = SCHEMAS.get(op)
    if model is None:
        return (None, [f"no argument schema for op {op!r}"]) if strict else (dict(args), [])
    try:
        return model.model_validate(args).model_dump(exclude_unset=True), []  # forward only what the caller set
    except ValidationError as exc:
        return None, [f"{'.'.join(str(p) for p in e['loc']) or '<args>'}: {e['msg']}" for e in exc.errors()]
