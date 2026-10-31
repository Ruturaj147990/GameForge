"""Level manifest schema for spatial queries and scenario generation (WI-3.5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field


class ManifestActor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: str
    tag: str
    cls: str
    entity_id: Optional[str] = None
    location: Tuple[float, float, float]
    yaw: float = 0.0


class LevelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["level_manifest/1"] = Field("level_manifest/1", alias="schema")
    level_id: str
    map: str
    player_start: Tuple[float, float, float]
    actors: List[ManifestActor] = Field(default_factory=list)

    def to_file(self, path: Union[str, Path]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        return p

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> LevelManifest:
        p = Path(path)
        return cls.model_validate_json(p.read_text(encoding="utf-8"))
