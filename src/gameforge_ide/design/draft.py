"""DesignDraft: the small schema a model fills. design/expand.py turns it into a full GDS."""
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from .gds import Biome, CameraKind, EntityKind, Genre, Lighting


class _D(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DraftEntity(_D):
    kind: EntityKind
    count: int = Field(ge=1, le=50)
    note: str = Field("", max_length=60)


class DraftWin(_D):
    type: Literal["collect_all", "reach_goal", "defeat_all", "survive_seconds", "score_at_least",
                  "board_win", "match_win"]
    target: Optional[int] = Field(None, ge=1, le=10000)
    seconds: Optional[int] = Field(None, ge=1, le=3600)


class DraftLose(_D):
    type: Literal["health_zero", "timer_runs_out", "fall_off", "board_loss", "match_loss", "caught_by_guard"]
    seconds: Optional[int] = Field(None, ge=1, le=3600)
    target: Optional[int] = Field(None, ge=0, le=10000)


class DesignDraft(_D):
    title: str = Field(min_length=1, max_length=60)
    genre: Genre
    camera: CameraKind
    pitch: str = Field("", max_length=280)
    biome: Biome = Biome.NONE
    lighting: Lighting = Lighting.DAY
    level_size: Literal["small", "medium", "large"] = "small"
    entities: List[DraftEntity] = Field(default_factory=list, max_length=12)
    win: List[DraftWin] = Field(min_length=1, max_length=3)
    lose: List[DraftLose] = Field(default_factory=list, max_length=3)
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    art_style: Literal["stylized", "realistic", "low_poly", "toon"] = "stylized"
    music_mood: Literal["none", "calm", "tense", "heroic", "playful"] = "none"
    custom_rules: List[str] = Field(default_factory=list, max_length=3)
    questions: List[str] = Field(default_factory=list, max_length=3)
