"""Scenario schemas for deterministic QA replay and assertions (WI-3.5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── Step Arguments ────────────────────────────────────────────────────────────

class NavigateToArgs(_Base):
    tag: str
    accept_radius_cm: float = 120.0
    timeout_s: float = 60.0


class NavigateToPointArgs(_Base):
    x: float
    y: float
    z: float
    accept_radius_cm: float = 120.0
    timeout_s: float = 60.0


class InjectArgs(_Base):
    action: str
    value: Union[bool, float, List[float]]
    hold_s: float = 0.0


class WaitEventArgs(_Base):
    e: str
    count: int = 1
    entity: Optional[str] = None
    timeout_s: float = 30.0


class WaitArgs(_Base):
    seconds: float


class SelectActorArgs(_Base):
    tag: str


class LookAtArgs(_Base):
    tag: str


# ── Steps (Single-key union) ──────────────────────────────────────────────────

class NavigateToStep(_Base):
    navigate_to: NavigateToArgs


class NavigateToPointStep(_Base):
    navigate_to_point: NavigateToPointArgs


class InjectStep(_Base):
    inject: InjectArgs


class WaitEventStep(_Base):
    wait_event: WaitEventArgs


class WaitStep(_Base):
    wait_s: WaitArgs


class SelectActorStep(_Base):
    select_actor: SelectActorArgs


class LookAtStep(_Base):
    look_at: LookAtArgs


Step = Union[
    NavigateToStep,
    NavigateToPointStep,
    InjectStep,
    WaitEventStep,
    WaitStep,
    SelectActorStep,
    LookAtStep,
]


# ── Expectations ──────────────────────────────────────────────────────────────

class EventExpectation(_Base):
    event: str
    entity: Optional[str] = None


class EventCountExpectation(_Base):
    event_count: str
    min: int = 0
    max: Optional[int] = None
    entity: Optional[str] = None


class NoEventExpectation(_Base):
    no_event: str


class LegsOkExpectation(_Base):
    legs_ok: bool = True


Expectation = Union[
    EventExpectation,
    EventCountExpectation,
    NoEventExpectation,
    LegsOkExpectation,
]


# ── Captures ──────────────────────────────────────────────────────────────────

class Capture(_Base):
    on_event: str
    screenshot: str


# ── Scenario ──────────────────────────────────────────────────────────────────

class Scenario(_Base):
    schema_: Literal["scenario/1"] = Field("scenario/1", alias="schema")
    scenario_id: str
    description: Optional[str] = None
    timeout_s: float = 120.0
    steps: List[Step] = Field(default_factory=list)
    expect: List[Expectation] = Field(default_factory=list)
    captures: List[Capture] = Field(default_factory=list)

    def to_file(self, path: Union[str, Path]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        return p

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> Scenario:
        p = Path(path)
        return cls.model_validate_json(p.read_text(encoding="utf-8"))


# ── Result Schemas ────────────────────────────────────────────────────────────

class StepResultRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    i: int
    kind: str
    status: str  # DONE | FAILED | SKIPPED | RUNNING
    t0: float
    t1: Optional[float] = None
    error: Optional[str] = None
    detail: Dict[str, Any] = Field(default_factory=dict)


class LegRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    target: str
    distance_cm: float
    seconds: float
    max_step_cm: float
    result: str


class ExpectResultRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    expect: Union[str, Dict[str, Any]]
    ok: bool
    observed: int = 0


class BuildInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    configuration: str
    engine: str = "5.7.4"


class ScenarioResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    schema_: Literal["scenario_result/1"] = Field("scenario_result/1", alias="schema")
    scenario_id: str
    passed: bool
    duration_s: float = 0.0
    start_delay_s: float = 0.0
    build: Optional[BuildInfo] = None
    steps: List[StepResultRecord] = Field(default_factory=list)
    legs: List[LegRecord] = Field(default_factory=list)
    expect: List[ExpectResultRecord] = Field(default_factory=list)
    failures: List[str] = Field(default_factory=list)
    events_file: Optional[str] = None

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> ScenarioResult:
        p = Path(path)
        return cls.model_validate_json(p.read_text(encoding="utf-8"))
