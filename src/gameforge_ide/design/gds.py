"""Game Design Spec, schema gds/1 (AD-9). The single contract between user, models, composer and QA."""
from __future__ import annotations

import re
import secrets
import time
from enum import Enum
from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .events_catalog import EVENT_RE, MODULE_EVENTS, STAT_RE, all_events

SCHEMA_VERSION = "gds/1"
IDENT = r"^[a-z][a-z0-9_]{0,39}$"
EVENT = EVENT_RE.pattern
STAT = STAT_RE.pattern
PASCAL = r"^[A-Z][A-Za-z0-9]{1,30}$"
_UNSAFE = re.compile(r'["\\\r\n]')

Scalar = Union[bool, int, float, str]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _safe(v: str) -> str:
    if _UNSAFE.search(v):
        raise ValueError("text must not contain quotes, backslashes or newlines")
    return v


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Genre(str, Enum):
    GRID_BOARD = "grid_board"; PLATFORMER = "platformer"; ARENA_COMBAT = "arena_combat"
    CARD_BATTLER = "card_battler"; EXPLORATION = "exploration"; ACTION_ADVENTURE = "action_adventure"
    TOP_DOWN_SHOOTER = "top_down_shooter"; DUNGEON_CRAWLER = "dungeon_crawler"; PUZZLE = "puzzle"; CUSTOM = "custom"


class CameraKind(str, Enum):
    THIRD_PERSON = "third_person"; TOP_DOWN = "top_down"; FIRST_PERSON = "first_person"
    SIDE_SCROLLER = "side_scroller"; FIXED_BOARD = "fixed_board"


class LayoutKind(str, Enum):
    BOARD = "board"; ARENA = "arena"; COURSE = "course"; ROOMS = "rooms"; OPEN_WORLD = "open_world"; LANES = "lanes"


class Biome(str, Enum):
    NONE = "none"; FOREST = "forest"; DESERT = "desert"; ISLAND = "island"; MOUNTAIN = "mountain"
    DUNGEON = "dungeon"; INDOOR = "indoor"


class Lighting(str, Enum):
    DAY = "day"; DUSK = "dusk"; NIGHT = "night"; INDOOR = "indoor"


class EntityKind(str, Enum):
    PLAYER = "player"; PICKUP = "pickup"; CHECKPOINT = "checkpoint"; GOAL = "goal"; HAZARD = "hazard"
    ENEMY = "enemy"; RANGED_ENEMY = "ranged_enemy"; SPAWNER = "spawner"; GUARD = "guard"; NPC = "npc"
    DOOR = "door"; SWITCH = "switch"; MOVING_PLATFORM = "moving_platform"; LANDMARK = "landmark"; PROP = "prop"
    BOARD = "board"; CARD_TABLE = "card_table"


class Vec2(_M):
    x: float = Field(ge=10, le=2000)
    y: float = Field(ge=10, le=2000)


class Vec3(_M):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class Meta(_M):
    schema_version: Literal["gds/1"] = SCHEMA_VERSION
    gds_id: str = Field(default_factory=lambda: "gds_" + secrets.token_hex(6), pattern=r"^gds_[0-9a-f]{12}$")
    revision: int = Field(1, ge=1)
    project_name: str = Field(pattern=PASCAL)
    title: str = Field(min_length=1, max_length=60)
    source_prompt: str = Field("", max_length=4000)
    generator: str = Field("user", pattern=r"^(user|preset:[a-z_]+|model:[\w.:\-/]+|patch)$")
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)

    @field_validator("title")
    @classmethod
    def _title_safe(cls, v: str) -> str:
        return _safe(v)


class Overview(_M):
    genre: Genre
    pitch: str = Field("", max_length=280)
    camera: CameraKind
    players: Literal[1, 2] = 1
    session_minutes: int = Field(10, ge=1, le=120)


class LevelSpec(_M):
    level_id: str = Field(pattern=IDENT)
    layout: LayoutKind
    size_m: Vec2
    biome: Biome = Biome.NONE
    lighting: Lighting = Lighting.DAY
    seed: int = Field(0, ge=0, le=2**31 - 1)
    layout_params: Dict[str, Scalar] = Field(default_factory=dict)


class Scene(_M):
    levels: List[LevelSpec] = Field(min_length=1, max_length=8)
    start_level: str = Field(pattern=IDENT)

    @model_validator(mode="after")
    def _levels(self):
        ids = [lv.level_id for lv in self.levels]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate level_id")
        if self.start_level not in ids:
            raise ValueError(f"start_level {self.start_level!r} is not a level")
        return self


class Placement(_M):
    strategy: Literal["fixed", "scatter", "path", "grid", "slot"] = "scatter"
    points_m: List[Vec3] = Field(default_factory=list, max_length=500)
    min_spacing_m: float = Field(2.0, ge=0.2, le=500)
    slot: Optional[str] = Field(None, pattern=IDENT)


class EntitySpec(_M):
    entity_id: str = Field(pattern=IDENT)
    kind: EntityKind
    module: str = Field(pattern=r"^kit\.[a-z_]+$")
    level_id: str = Field(pattern=IDENT)
    count: int = Field(1, ge=1, le=500)
    placement: Placement = Field(default_factory=Placement)
    props: Dict[str, Union[Scalar, List[Scalar]]] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def _placement(self):
        if self.placement.strategy == "fixed" and len(self.placement.points_m) != self.count:
            raise ValueError(f"{self.entity_id}: fixed placement needs exactly count={self.count} points")
        if self.placement.strategy == "slot" and not self.placement.slot:
            raise ValueError(f"{self.entity_id}: slot placement needs a slot name")
        if self.module not in MODULE_EVENTS:
            raise ValueError(f"{self.entity_id}: unknown kit module {self.module!r}")
        return self


class InputActionSpec(_M):
    action_id: str = Field(pattern=r"^IA_[A-Za-z0-9]{1,30}$")
    value_type: Literal["bool", "axis1d", "axis2d"]
    bindings: List[str] = Field(min_length=1, max_length=8)
    purpose: str = Field("", max_length=80)

    @field_validator("bindings")
    @classmethod
    def _keys(cls, v: List[str]) -> List[str]:
        bad = [k for k in v if not re.fullmatch(r"[A-Za-z0-9_]+(:[A-Za-z0-9_+\-]+)?", k)]
        if bad:
            raise ValueError(f"invalid key names {bad}; use Unreal key names, optionally with :modifier")
        return v


class InputSpec(_M):
    actions: List[InputActionSpec] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def _unique(self):
        ids = [a.action_id for a in self.actions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate action_id")
        return self


class EventRef(_M):
    event: str = Field(pattern=EVENT)
    source: Optional[str] = Field(None, pattern=IDENT)


# ── conditions (no free-text logic, no eval) ───────────────────────────────────
class CountAtLeast(_M):
    kind: Literal["count_at_least"] = "count_at_least"
    event: str = Field(pattern=EVENT)
    n: int = Field(ge=1, le=10000)
    source: Optional[str] = Field(None, pattern=IDENT)


class StatCompare(_M):
    kind: Literal["stat"] = "stat"
    stat: str = Field(pattern=STAT)
    op: Literal["<", "<=", "==", ">=", ">"]
    value: float


class TimerElapsed(_M):
    kind: Literal["timer"] = "timer"
    seconds: float = Field(ge=1, le=7200)


class EventOccurred(_M):
    kind: Literal["event"] = "event"
    event: str = Field(pattern=EVENT)
    source: Optional[str] = Field(None, pattern=IDENT)


class AllOf(_M):
    kind: Literal["all"] = "all"
    items: List["Condition"] = Field(min_length=1, max_length=8)


class AnyOf(_M):
    kind: Literal["any"] = "any"
    items: List["Condition"] = Field(min_length=1, max_length=8)


Condition = Annotated[Union[CountAtLeast, StatCompare, TimerElapsed, EventOccurred, AllOf, AnyOf],
                      Field(discriminator="kind")]
AllOf.model_rebuild()
AnyOf.model_rebuild()


# ── effects ────────────────────────────────────────────────────────────────────
class AddStat(_M):
    kind: Literal["add_stat"] = "add_stat"
    stat: str = Field(pattern=STAT)
    delta: float


class SetStat(_M):
    kind: Literal["set_stat"] = "set_stat"
    stat: str = Field(pattern=STAT)
    value: float


class Emit(_M):
    kind: Literal["emit"] = "emit"
    event: str = Field(pattern=EVENT)


class Spawn(_M):
    kind: Literal["spawn"] = "spawn"
    entity_id: str = Field(pattern=IDENT)
    count: int = Field(1, ge=1, le=100)


class Message(_M):
    kind: Literal["message"] = "message"
    text: str = Field(min_length=1, max_length=80)
    seconds: float = Field(3.0, ge=0.5, le=10)

    @field_validator("text")
    @classmethod
    def _text_safe(cls, v: str) -> str:
        return _safe(v)


class EndGame(_M):
    kind: Literal["end_game"] = "end_game"
    outcome: Literal["win", "lose"]


class CustomCode(_M):
    kind: Literal["custom_code"] = "custom_code"
    description: str = Field(min_length=10, max_length=400)
    handler_name: str = Field(pattern=r"^[A-Z][A-Za-z0-9]{2,40}Rule$")


Effect = Annotated[Union[AddStat, SetStat, Emit, Spawn, Message, EndGame, CustomCode], Field(discriminator="kind")]


class RuleSpec(_M):
    rule_id: str = Field(pattern=IDENT)
    when: EventRef
    conditions: List[Condition] = Field(default_factory=list, max_length=8)
    effects: List[Effect] = Field(min_length=1, max_length=8)
    description: str = Field("", max_length=200)


class PhaseSpec(_M):
    phase_id: str = Field(pattern=IDENT)
    description: str = Field("", max_length=200)
    enter_when: Optional[Condition] = None
    params: Dict[str, Scalar] = Field(default_factory=dict)


class Progression(_M):
    phases: List[PhaseSpec] = Field(default_factory=list, max_length=16)
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    difficulty_params: Dict[str, Scalar] = Field(default_factory=dict)


class ScoreSpec(_M):
    stat: str = Field("game.score", pattern=STAT)
    show_in_hud: bool = True


class Goals(_M):
    win: List[Condition] = Field(default_factory=list, max_length=8)
    lose: List[Condition] = Field(default_factory=list, max_length=8)
    score: Optional[ScoreSpec] = None
    sandbox: bool = False

    @model_validator(mode="after")
    def _has_end(self):
        if not self.win and not self.sandbox:
            raise ValueError("goals.win is empty; add a win condition or set sandbox=true")
        return self


class FeedbackSpec(_M):
    on: EventRef
    vfx: Optional[str] = Field(None, pattern=r"^vfx\.[a-z_]+$")
    sfx: Optional[str] = Field(None, pattern=r"^sfx\.[a-z_]+$")
    camera_shake: float = Field(0.0, ge=0, le=1)
    ui_message: Optional[str] = Field(None, max_length=60)


class HudElement(_M):
    element_id: str = Field(pattern=IDENT)
    kind: Literal["bar", "counter", "text", "timer", "objective"]
    binds: Optional[str] = Field(None, pattern=STAT)
    label: str = Field("", max_length=30)


class UISpec(_M):
    hud: List[HudElement] = Field(default_factory=list, max_length=12)
    main_menu: bool = True
    pause_menu: bool = True
    end_screen: bool = True


class ArtDirection(_M):
    style: Literal["stylized", "realistic", "low_poly", "toon"] = "stylized"
    palette: List[str] = Field(default_factory=lambda: ["#2E3440", "#88C0D0", "#EBCB8B", "#BF616A"],
                               min_length=2, max_length=8)
    material_theme: str = Field("default", pattern=IDENT)
    character_source: Literal["procedural", "mannequin", "metahuman", "library"] = "mannequin"
    placeholder_ok: bool = False  # P7 flipped default to False per AD-17

    @field_validator("palette")
    @classmethod
    def _hex(cls, v):
        if any(not re.fullmatch(r"#[0-9A-Fa-f]{6}", c) for c in v):
            raise ValueError("palette entries must be #RRGGBB")
        return v


class AudioSpec(_M):
    music_mood: Literal["none", "calm", "tense", "heroic", "playful"] = "none"
    ambience: Literal["none", "wind", "forest", "dungeon", "city"] = "none"
    sfx_set: Literal["default", "retro", "soft"] = "default"


class TechSpec(_M):
    target_fps: Literal[30, 60] = 60
    max_frame_ms: float = Field(16.6, ge=8, le=50)
    max_package_mb: int = Field(1200, ge=100, le=4000)   # P10 lowers the default to 400
    multiplayer: Literal["none", "listen_server"] = "none"


class ScenarioRef(_M):
    scenario_id: str = Field(pattern=IDENT)
    derived_from: str = Field(pattern=r"^(goals\.(win|lose)\[\d+\]|user|smoke)$")
    must_pass: bool = True


class Acceptance(_M):
    scenarios: List[ScenarioRef] = Field(default_factory=list, max_length=32)
    vision_rubric_min: float = Field(0.0, ge=0, le=1)
    extra_checks: List[str] = Field(default_factory=list, max_length=16)


class GameDesignSpec(_M):
    meta: Meta
    overview: Overview
    scene: Scene
    entities: List[EntitySpec] = Field(default_factory=list, max_length=200)
    input: InputSpec = Field(default_factory=InputSpec)
    rules: List[RuleSpec] = Field(default_factory=list, max_length=64)
    progression: Progression = Field(default_factory=Progression)
    goals: Goals
    feedback: List[FeedbackSpec] = Field(default_factory=list, max_length=32)
    ui: UISpec = Field(default_factory=UISpec)
    art: ArtDirection = Field(default_factory=ArtDirection)
    audio: AudioSpec = Field(default_factory=AudioSpec)
    tech: TechSpec = Field(default_factory=TechSpec)
    acceptance: Acceptance = Field(default_factory=Acceptance)

    # ---- cross-reference validation -------------------------------------------------------
    def _declared_events(self) -> set[str]:
        used_modules = {e.module for e in self.entities}
        events = set(all_events()) if not used_modules else set()
        events |= {"game.started", "game.won", "game.lost", "game.restarted", "game.paused", "game.resumed"}
        for m in used_modules:
            events |= set(MODULE_EVENTS[m])
        for r in self.rules:
            events |= {eff.event for eff in r.effects if isinstance(eff, Emit)}
        return events

    @model_validator(mode="after")
    def _cross_refs(self):
        errs: List[str] = []
        level_ids = {lv.level_id for lv in self.scene.levels}
        ent_ids = [e.entity_id for e in self.entities]
        if len(ent_ids) != len(set(ent_ids)):
            errs.append("duplicate entity_id")
        ent_set = set(ent_ids)
        for e in self.entities:
            if e.level_id not in level_ids:
                errs.append(f"entity {e.entity_id}: unknown level {e.level_id}")

        # Lazy entity props validation against KitModule params_model (WI-5.14)
        try:
            from ..kit.registry import KIT
            for e in self.entities:
                if e.module in KIT:
                    mod = KIT[e.module]
                    try:
                        mod.params_model.model_validate(e.props)
                    except Exception as ex:
                        errs.append(f"entity {e.entity_id} props invalid for {e.module}: {ex}")
        except Exception:
            pass

        events = self._declared_events()

        def check_cond(c, where: str) -> None:
            if isinstance(c, (AllOf, AnyOf)):
                for i, sub in enumerate(c.items):
                    check_cond(sub, f"{where}.items[{i}]")
                return
            ev = getattr(c, "event", None)
            if ev and ev not in events:
                errs.append(f"{where}: event {ev!r} is not emitted by any module in this game")
            src = getattr(c, "source", None)
            if src and src not in ent_set:
                errs.append(f"{where}: unknown source entity {src!r}")
            stat = getattr(c, "stat", None)
            if stat and stat.startswith("entity.") and stat.split(".")[1] not in ent_set:
                errs.append(f"{where}: stat {stat!r} names an unknown entity")

        for i, c in enumerate(self.goals.win):
            check_cond(c, f"goals.win[{i}]")
        for i, c in enumerate(self.goals.lose):
            check_cond(c, f"goals.lose[{i}]")
        for r in self.rules:
            if r.when.event not in events:
                errs.append(f"rule {r.rule_id}: trigger event {r.when.event!r} is not emitted in this game")
            if r.when.source and r.when.source not in ent_set:
                errs.append(f"rule {r.rule_id}: unknown source {r.when.source!r}")
            for i, c in enumerate(r.conditions):
                check_cond(c, f"rule {r.rule_id}.conditions[{i}]")
            for eff in r.effects:
                if isinstance(eff, Spawn) and eff.entity_id not in ent_set:
                    errs.append(f"rule {r.rule_id}: spawn of unknown entity {eff.entity_id!r}")
        for f in self.feedback:
            if f.on.event not in events:
                errs.append(f"feedback: event {f.on.event!r} is not emitted in this game")
        rule_ids = [r.rule_id for r in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            errs.append("duplicate rule_id")
        if self.overview.players == 2 and self.tech.multiplayer == "none" and \
                self.overview.genre not in (Genre.GRID_BOARD, Genre.CARD_BATTLER):
            errs.append("players=2 needs tech.multiplayer=listen_server (hot-seat is only for board/card games)")
        if errs:
            raise ValueError("; ".join(errs))
        return self

    def to_json(self) -> str:
        return self.model_dump_json(indent=1)
