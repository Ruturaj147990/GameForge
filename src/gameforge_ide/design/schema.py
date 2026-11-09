"""Canonical Design Schema module for GameForge (schema gds/1.1 and DesignDraft).

Exports the authoritative Game Design Spec models, DesignDraft models,
and schema validation helpers.
"""
from __future__ import annotations

from typing import Any, Dict, Union

from .draft import DesignDraft, DraftEntity, DraftLose, DraftWin
from .gds import (
    Acceptance,
    AddStat,
    AllOf,
    AnyOf,
    ArchitectureSpec,
    ArtDirection,
    AudioSpec,
    Biome,
    CameraKind,
    Condition,
    CountAtLeast,
    CustomCode,
    Effect,
    Emit,
    EndGame,
    EntityKind,
    EntitySpec,
    EventOccurred,
    EventRef,
    FeedbackSpec,
    GameDesignSpec,
    Genre,
    Goals,
    HudElement,
    InputActionSpec,
    InputSpec,
    IntroSpec,
    LayoutKind,
    LevelSpec,
    Lighting,
    Message,
    Meta,
    Overview,
    PhaseSpec,
    Placement,
    PresentationSpec,
    Progression,
    RuleSpec,
    ScenarioRef,
    Scene,
    ScoreSpec,
    SetStat,
    Spawn,
    StatCompare,
    TechSpec,
    TimerElapsed,
    UISpec,
    Vec2,
    Vec3,
)

__all__ = [
    "GameDesignSpec",
    "DesignDraft",
    "Meta",
    "Overview",
    "Scene",
    "LevelSpec",
    "EntitySpec",
    "Placement",
    "InputSpec",
    "InputActionSpec",
    "RuleSpec",
    "Condition",
    "CountAtLeast",
    "StatCompare",
    "TimerElapsed",
    "EventOccurred",
    "AllOf",
    "AnyOf",
    "Effect",
    "AddStat",
    "SetStat",
    "Emit",
    "Spawn",
    "Message",
    "EndGame",
    "CustomCode",
    "Progression",
    "PhaseSpec",
    "Goals",
    "ScoreSpec",
    "FeedbackSpec",
    "UISpec",
    "HudElement",
    "ArtDirection",
    "AudioSpec",
    "IntroSpec",
    "PresentationSpec",
    "TechSpec",
    "Acceptance",
    "ArchitectureSpec",
    "ScenarioRef",
    "Vec2",
    "Vec3",
    "EventRef",
    "DraftEntity",
    "DraftLose",
    "DraftWin",
    "Genre",
    "CameraKind",
    "LayoutKind",
    "Biome",
    "Lighting",
    "EntityKind",
    "validate_gds",
    "validate_draft",
    "gds_json_schema",
    "draft_json_schema",
]


def validate_gds(data: Union[str, Dict[str, Any]]) -> GameDesignSpec:
    """Validate a JSON string or dict against GameDesignSpec schema."""
    if isinstance(data, str):
        return GameDesignSpec.model_validate_json(data)
    return GameDesignSpec.model_validate(data)


def validate_draft(data: Union[str, Dict[str, Any]]) -> DesignDraft:
    """Validate a JSON string or dict against DesignDraft schema."""
    if isinstance(data, str):
        return DesignDraft.model_validate_json(data)
    return DesignDraft.model_validate(data)


def gds_json_schema() -> Dict[str, Any]:
    """Return the JSON Schema for GameDesignSpec."""
    return GameDesignSpec.model_json_schema()


def draft_json_schema() -> Dict[str, Any]:
    """Return the JSON Schema for DesignDraft."""
    return DesignDraft.model_json_schema()
