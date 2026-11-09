"""DesignDraft: the compact schema a model fills. design/expand.py turns it into a full GDS."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .gds import Biome, CameraKind, EntityKind, Genre, Lighting


class _D(BaseModel):
    model_config = ConfigDict(extra="forbid")


_WIN_ALIASES: Dict[str, str] = {
    "collect": "collect_all",
    "collect_items": "collect_all",
    "collect_pickups": "collect_all",
    "gather_all": "collect_all",
    "goal": "reach_goal",
    "exit": "reach_goal",
    "reach_exit": "reach_goal",
    "finish": "reach_goal",
    "defeat": "defeat_all",
    "kill_all": "defeat_all",
    "clear_waves": "defeat_all",
    "defeat_enemies": "defeat_all",
    "survive": "survive_seconds",
    "survival": "survive_seconds",
    "timer": "survive_seconds",
    "score": "score_at_least",
    "points": "score_at_least",
    "high_score": "score_at_least",
    "board": "board_win",
    "puzzle_solved": "board_win",
    "match": "match_win",
}

_LOSE_ALIASES: Dict[str, str] = {
    "death": "health_zero",
    "die": "health_zero",
    "player_died": "health_zero",
    "no_health": "health_zero",
    "timeout": "timer_runs_out",
    "time_limit": "timer_runs_out",
    "time_expired": "timer_runs_out",
    "fall": "fall_off",
    "pit": "fall_off",
    "board": "board_loss",
    "match": "match_loss",
    "caught": "caught_by_guard",
    "spotted": "caught_by_guard",
    "detected": "caught_by_guard",
}


class DraftEntity(_D):
    kind: EntityKind
    count: int = Field(ge=1, le=50)
    note: str = Field("", max_length=120)
    props: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().lower().replace("-", "_").replace(" ", "_")
            return v_clean
        return v


class DraftWin(_D):
    type: Literal[
        "collect_all",
        "reach_goal",
        "defeat_all",
        "survive_seconds",
        "score_at_least",
        "board_win",
        "match_win",
    ]
    target: Optional[int] = Field(None, ge=1, le=10000)
    seconds: Optional[int] = Field(None, ge=1, le=3600)

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_win_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            cleaned = v.strip().lower().replace("-", "_").replace(" ", "_")
            return _WIN_ALIASES.get(cleaned, cleaned)
        return v


class DraftLose(_D):
    type: Literal[
        "health_zero",
        "timer_runs_out",
        "fall_off",
        "board_loss",
        "match_loss",
        "caught_by_guard",
    ]
    seconds: Optional[int] = Field(None, ge=1, le=3600)
    target: Optional[int] = Field(None, ge=0, le=10000)

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_lose_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            cleaned = v.strip().lower().replace("-", "_").replace(" ", "_")
            return _LOSE_ALIASES.get(cleaned, cleaned)
        return v


class DesignDraft(_D):
    title: str = Field(min_length=1, max_length=60)
    genre: Genre
    camera: CameraKind
    pitch: str = Field("", max_length=280)
    biome: Biome = Biome.NONE
    lighting: Lighting = Lighting.DAY
    level_size: Literal["small", "medium", "large"] = "small"
    entities: List[DraftEntity] = Field(default_factory=list, max_length=24)
    win: List[DraftWin] = Field(min_length=1, max_length=3)
    lose: List[DraftLose] = Field(default_factory=list, max_length=3)
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    art_style: Literal["stylized", "realistic", "low_poly", "toon"] = "stylized"
    music_mood: Literal["none", "calm", "tense", "heroic", "playful"] = "none"
    custom_rules: List[str] = Field(default_factory=list, max_length=10)
    questions: List[str] = Field(default_factory=list, max_length=3)
    architecture: Optional[Dict[str, Any]] = Field(default=None)

    @field_validator("camera", mode="before")
    @classmethod
    def _normalize_camera(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().lower().replace("-", "_").replace(" ", "_")
        return v

    @field_validator("genre", mode="before")
    @classmethod
    def _normalize_genre(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().lower().replace("-", "_").replace(" ", "_")
        return v

    @field_validator("biome", mode="before")
    @classmethod
    def _normalize_biome(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().lower().replace("-", "_")
        return v

    @field_validator("lighting", mode="before")
    @classmethod
    def _normalize_lighting(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().lower().replace("-", "_")
        return v
