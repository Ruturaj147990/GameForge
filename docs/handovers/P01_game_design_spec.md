# P1 — Game Design Spec `gds/1` (handover)

**Branch:** `master` (no feature branches). **Depends on:** P0 accepted. **Resolves:** audit F-02. **Decision:** AD-9.
**Estimate:** 1.5–2 weeks. **Read first:** `../01_ARCHITECTURE.md` §3.1–3.2, `../03_RESEARCH_2026-10-31.md` R10–R11.

## Objective

Every game GameForge builds is described by one typed, validated, reviewable document: the **Game Design Spec**.
In this phase the GDS is created from prompts, rendered for humans, validated, versioned, and accepted by the
**existing** recipe pipeline through a legacy adapter. That proves the contract end to end before the composer (P6)
replaces recipes.

### Key design choice: the model writes a small draft; code expands it to a full GDS

Local 4B/9B models cannot reliably fill a 150-field nested schema. They *can* fill a short `DesignDraft` (about 15
fields, mostly enums). A deterministic expander (`design/expand.py`) turns a draft into a full GDS using genre
templates. The result:
- A model's output can only choose between options that the expander knows how to build.
- Rules and termination conditions (the weakest area in the literature) come from tested templates, not model prose.
- Hosted heavy models use the same draft path in P1. P9 decides whether strong models may emit full GDS patches.

## Files created in this phase

```
src/gameforge_ide/design/__init__.py
src/gameforge_ide/design/gds.py              # schema (canonical, below)
src/gameforge_ide/design/events_catalog.py   # built-in events, stats, planned kit modules and their events
src/gameforge_ide/design/draft.py            # DesignDraft schema (model-facing)
src/gameforge_ide/design/expand.py           # DesignDraft → GameDesignSpec (deterministic)
src/gameforge_ide/design/presets.py          # 5 presets that reproduce the legacy recipes
src/gameforge_ide/design/prompt_to_gds.py    # orchestrates: preset match → model draft → expand → validate
src/gameforge_ide/design/render.py           # Markdown summary + rule sentences
src/gameforge_ide/design/store.py            # load/save/revision history under <project>/GameForge/design/
src/gameforge_ide/design/legacy.py           # GDS → legacy recipe params (bridge until P6)
src/gameforge_ide/desktop/panels/design_panel.py   # minimal Design view (P4 replaces it with the full editor)
tests/unit/test_gds_schema.py  test_gds_expand.py  test_prompt_to_gds.py  test_gds_legacy.py  test_gds_store.py
tests/fixtures/gds_prompts.jsonl             # 40 prompts with expected outcomes
```

Modified: `backend/providers/ollama_provider.py` (adds `complete_json`), `backend/tools/game_tools.py`
(`plan_game` and `propose_create_game` produce a GDS), `pipeline/game_pipeline.py` (accepts a GDS through the legacy
adapter), `desktop/panels/approval_card.py` (shows the GDS summary).

---

## WI-1.1 `design/events_catalog.py`

This catalogue is shared by the validator, the scenario generator (P3) and the kit (P5). The C++ header
`GameForgeEventNames.h` (P3) must list the same strings, and a unit test in P3 enforces that.

```python
"""Built-in GameForge event names, stats and the planned kit modules (P5) with the events they emit."""
from __future__ import annotations
import re

EVENT_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
STAT_RE = re.compile(r"^(player\.(health|max_health|stamina|lives)"
                     r"|game\.(score|time_s|counter\.[a-z][a-z0-9_]*)"
                     r"|entity\.[a-z][a-z0-9_]*\.(remaining|collected|killed))$")

GAME_EVENTS = ("game.started", "game.won", "game.lost", "game.restarted", "game.paused", "game.resumed")

# module_id -> events it emits. Status of each module lives in kit/registry.py (P5); here only names.
MODULE_EVENTS: dict[str, tuple[str, ...]] = {
    "kit.player_character": ("player.spawned", "player.damaged", "player.died", "player.respawned", "player.jumped"),
    "kit.pickup": ("pickup.collected",),
    "kit.checkpoint": ("checkpoint.reached",),
    "kit.goal": ("goal.reached",),
    "kit.hazard": ("hazard.touched",),
    "kit.enemy_melee": ("enemy.spawned", "enemy.attacked", "enemy.killed"),
    "kit.enemy_ranged": ("enemy.spawned", "enemy.attacked", "enemy.killed"),
    "kit.spawner": ("wave.started", "wave.cleared"),
    "kit.guard": ("guard.state", "guard.spotted_player", "guard.lost_player"),
    "kit.quest_giver": ("dialogue.line",),
    "kit.objective": ("objective.started", "objective.updated", "objective.completed", "save.loaded", "save.written"),
    "kit.door": ("interact.used", "door.opened", "door.closed"),
    "kit.switch": ("interact.used", "switch.toggled"),
    "kit.moving_platform": (),
    "kit.landmark": ("landmark.discovered",),
    "kit.prop": (),
    "kit.grid_board": ("board.move", "board.win", "board.draw", "turn.ended"),
    "kit.card_match": ("card.played", "turn.ended", "lane.resolved", "match.won", "match.lost"),
}

# EntityKind -> default module (the expander's choice when a draft gives only a kind)
DEFAULT_MODULE: dict[str, str] = {
    "player": "kit.player_character", "pickup": "kit.pickup", "checkpoint": "kit.checkpoint", "goal": "kit.goal",
    "hazard": "kit.hazard", "enemy": "kit.enemy_melee", "ranged_enemy": "kit.enemy_ranged", "spawner": "kit.spawner",
    "guard": "kit.guard", "npc": "kit.quest_giver", "door": "kit.door", "switch": "kit.switch",
    "moving_platform": "kit.moving_platform", "landmark": "kit.landmark", "prop": "kit.prop",
    "board": "kit.grid_board", "card_table": "kit.card_match",
}

def all_events() -> frozenset[str]:
    return frozenset(GAME_EVENTS).union(*MODULE_EVENTS.values())
```

**Test:** every value in `MODULE_EVENTS` matches `EVENT_RE`; every `DEFAULT_MODULE` value is a key of `MODULE_EVENTS`.

---

## WI-1.2 `design/gds.py` (canonical schema)

Copy it verbatim. The field names are a contract with P3, P5, P6 and P8. Only Claude may change them.

```python
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
    placeholder_ok: bool = True  # P7 flips the default to False

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
```

**Notes for the implementer:**
- Validator methods may start with an underscore because they are decorated with `@field_validator`. Never attach
  validators as plain class attributes with a leading underscore: pydantic v2 treats those as private attributes and
  silently ignores them.
- `_declared_events`: if a GDS has **no** entities (a pure-rules prototype), every catalogue event is allowed.
  Otherwise only the events of the modules it uses, plus game events, plus events emitted by its own rules.

**Tests (`test_gds_schema.py`):** valid minimal GDS round-trips through `model_dump_json` and `model_validate_json`; each
cross-reference error raises with a message naming the offending element (unknown event, unknown entity in spawn,
duplicate ids, missing win without sandbox, fixed placement count mismatch, unknown module, unsafe title); a nested
`AllOf(AnyOf(CountAtLeast))` validates; `GameDesignSpec.model_json_schema()` succeeds and is ≤ 60 KB (it is shown to
hosted models in P9).

---

## WI-1.3 `design/draft.py` — the model-facing schema

```python
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


class DraftLose(_D):
    type: Literal["health_zero", "timer_runs_out", "fall_off", "board_loss", "match_loss", "caught_by_guard"]
    seconds: Optional[int] = Field(None, ge=5, le=3600)


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
```

---

## WI-1.4 `design/expand.py` — deterministic draft → GDS

**Algorithm (implement exactly):**
1. `project_name` = PascalCase of the title's alphanumeric words, truncated to 30 characters. If the first character
   is not a letter, prefix `Game`. Reuse `spec_from_prompt._pascal` if it already behaves this way. Read it, and do not
   duplicate it if it does.
2. A **genre template** supplies: the layout kind, default level size per `level_size`
   (`small=60×60 m`, `medium=150×150`, `large=400×400`), default input actions, HUD elements and feedback rows. The
   template table lives in `expand.py` as a dict `GENRE_TEMPLATES[Genre]`. Required entries:

| Genre | Layout | Camera default | Input actions (id: type: bindings) | Always-added entities |
|---|---|---|---|---|
| grid_board | board | fixed_board | `IA_Select: bool: LeftMouseButton` | `board` (kit.grid_board, slot "board") |
| platformer | course | third_person | `IA_Move: axis2d: W,S:negate,A:swizzle_negate,D:swizzle`; `IA_Look: axis2d: Mouse2D`; `IA_Jump: bool: SpaceBar` | `player` |
| arena_combat | arena | top_down | Move, Look, `IA_Attack: bool: LeftMouseButton`, `IA_Restart: bool: R` | `player`, `spawner` |
| card_battler | lanes | fixed_board | `IA_Select: bool: LeftMouseButton`, `IA_EndTurn: bool: E` | `card_table` |
| exploration / action_adventure | open_world (`biome` from draft, default forest) | third_person | Move, Look, Jump, `IA_Interact: bool: E` | `player` |
| top_down_shooter | arena | top_down | Move, Look, `IA_Fire: bool: LeftMouseButton` | `player`, `spawner` |
| dungeon_crawler | rooms | third_person | Move, Look, Interact, Attack | `player` |
| puzzle | board | fixed_board | Select | `board` |
| custom | arena | third_person | Move, Look, Jump, Interact | `player` |

   Binding modifiers use the syntax `Key:modifier` with modifiers `negate`, `swizzle` and `swizzle_negate`. P5 maps
   them to `UInputModifierNegate` and `UInputModifierSwizzleAxis(YXZ)`. Document this in the module docstring.
3. **Entities:** each `DraftEntity` → `EntitySpec(entity_id=f"{kind}s" if count>1 else kind (deduplicate with a _2
   suffix), kind, module=DEFAULT_MODULE[kind], level_id="level_1", count, placement=Placement(strategy="scatter"))`.
   The player gets `placement=Placement(strategy="slot", slot="player_start")`; goal → slot `"goal"`; board/card_table →
   slot `"board"`.
4. **Win conditions:**
   - `collect_all` → `CountAtLeast(event="pickup.collected", n=target or total pickups)`. If the draft has no pickup
     entity, the expander **adds** `pickups` with count = `target or 5`.
   - `reach_goal` → `EventOccurred(event="goal.reached")`, adding a `goal` entity if missing.
   - `defeat_all` → `StatCompare(stat="entity.<enemy_entity_id>.remaining", op="<=", value=0)`. The enemy entity must
     exist, otherwise add `enemies` count 5. With a spawner: `EventOccurred("wave.cleared")` combined with
     `StatCompare(stat="game.counter.waves_cleared", op=">=", value=<waves>)` through `AllOf`, plus a rule
     `on wave.cleared → add_stat game.counter.waves_cleared +1`.
   - `survive_seconds` → `TimerElapsed(seconds=target or 60)`.
   - `score_at_least` → `StatCompare(stat="game.score", op=">=", value=target or 100)`.
   - `board_win` → `EventOccurred("board.win")`. `match_win` → `EventOccurred("match.won")`.
5. **Lose conditions:** `health_zero` → `StatCompare("player.health","<=",0)`; `timer_runs_out` →
   `TimerElapsed(seconds)`, which is only valid if no win condition is also a timer (otherwise drop it and add a
   question); `fall_off` → `EventOccurred("player.died")`; `board_loss` → `EventOccurred("board.draw")` is NOT a loss,
   so use a rule `on board.win with source=ai → end_game lose` instead (see the grid preset); `match_loss` →
   `EventOccurred("match.lost")`; `caught_by_guard` → `EventOccurred("guard.spotted_player")`, adding a guard if missing.
6. **Rules always added:** `on pickup.collected → add_stat game.score +10` (if pickups exist);
   `on enemy.killed → add_stat game.score +25` (if enemies). Win and lose conditions are evaluated by the runtime
   from `goals`, not by rules.
7. **Custom rules:** each string → `RuleSpec(rule_id=f"custom_{i}", when=EventRef(event="game.started"),
   effects=[CustomCode(description=s, handler_name=f"Custom{i}Rule")])`.
8. **Acceptance:** one `ScenarioRef(scenario_id=f"win_{i}", derived_from=f"goals.win[{i}]")` per win condition and
   one `lose_{i}` per lose condition (`must_pass=True`), plus `ScenarioRef("smoke", "smoke")`.
9. HUD defaults: a health bar if `player` exists; a counter bound to `entity.pickups.collected` if pickups exist; a
   timer if any timer condition exists; a score counter if `goals.score`. The feedback defaults are the table below.
   (Preset names refer to P7 libraries. Until P7 they resolve to the existing template systems and procedural sounds.)

| Event | vfx | sfx |
|---|---|---|
| pickup.collected | vfx.sparkle_burst | sfx.pickup_chime |
| player.damaged | vfx.hit_flash | sfx.impact |
| enemy.killed | vfx.poof | sfx.defeat |
| game.won | vfx.confetti | sfx.fanfare |
| checkpoint.reached | vfx.ring | sfx.chime_low |

10. Validate with `GameDesignSpec.model_validate`. Expansion must never produce an invalid GDS from a valid draft: a
    property test (WI-1.9) checks this over 500 random drafts.

---

## WI-1.5 `design/presets.py` — the 5 legacy-equivalent presets

Each preset is `def preset_<id>(title: str | None = None, **overrides) -> GameDesignSpec`. It builds a `DesignDraft`
with values that reproduce the legacy recipe defaults, expands it, and then sets `entities[*].props` to the legacy
parameters so that `legacy.py` can map them back losslessly.

| Preset id | Legacy recipe | Draft | Entity props carrying legacy params |
|---|---|---|---|
| `tic_tac_toe` | grid_board_game | genre grid_board, win board_win, lose board_loss | `board.props = {board_size:3, win_length:3, vs_ai:true, gravity:false, ai_level:"perfect", cell_size_cm:200}` |
| `connect_four` | grid_board_game | same | `{board_size:7, win_length:4, gravity:true, ai_level:"greedy"}` |
| `gomoku` | grid_board_game | same | `{board_size:15, win_length:5}` |
| `platformer` | platformer | collect_all 5 + reach_goal, lose fall_off | `player.props = {player_speed:600, jump_velocity:650, gravity_scale:1.2, air_control:0.35, kill_z:-500}`; `pickups.count=5` |
| `arena_combat` | arena_combat | defeat_all via spawner (3 waves × 4), lose health_zero | `spawner.props = {wave_count:3, enemies_per_wave:4, enemy_max_health:50, enemy_attack_damage:15, enemy_attack_range:120, enemy_attack_cooldown:1.0, enemy_speed:350}`, `player.props = {player_max_health:100, player_attack_damage:35, player_attack_range:250, player_attack_cooldown:0.4}` |
| `card_battler` | card_battler | match_win, lose match_loss | `card_table.props = {player_base_health:30, opponent_base_health:30, starting_hand_size:4, max_hand_size:7, base_energy_per_turn:3, lane_count:3}` |
| `procedural_world` | procedural_world | genre exploration, reach_goal (landmark), sandbox false | level `layout_params = {terrain_type:"Valley", elevation_scale:1800, road_width:350, foliage_density:40, landmark_type:"Ruins"}`, `seed=2026`, entity `landmark` (kit.landmark, slot "landmark") |

For the grid lose condition, add the rule
`RuleSpec(rule_id="ai_wins", when=EventRef(event="board.win"), conditions=[StatCompare(stat="game.counter.ai_won", op=">=", value=1)], effects=[EndGame(outcome="lose")])`.
The board module (P5) sets `game.counter.ai_won` before emitting `board.win`. For P1 it only has to validate.

`PRESETS: dict[str, Callable[..., GameDesignSpec]]` and `PRESET_KEYWORDS: dict[str, list[str]]`, the latter moved from
`spec_from_prompt.RECIPES` (same keyword lists). The existing parameter regexes (`_SIZE`, `_WIN`, `_TARGET`,
`_WAVES`, `_ENEMIES`, `_HP`, `_NAME`, `_HOTSEAT`, `_AI_*`, `_DIFF`, `_SEED`, `_DENSITY`) are **imported** from
`spec_from_prompt` and applied as overrides. Do not copy them.

---

## WI-1.6 `design/prompt_to_gds.py`

```python
@dataclass
class PromptToGdsResult:
    status: Literal["OK", "NEEDS_INPUT", "UNSUPPORTED", "ERROR"]
    gds: Optional[GameDesignSpec] = None
    questions: List[str] = field(default_factory=list)
    path: Literal["preset", "model", "none"] = "none"
    model: Optional[str] = None
    attempts: int = 0
    errors: List[str] = field(default_factory=list)


def prompt_to_gds(prompt: str, complete_json: Optional[CompleteJson] = None, model: Optional[str] = None,
                  allow_model: bool = True) -> PromptToGdsResult: ...
```

`CompleteJson = Callable[[str, str, dict], Optional[str]]`, with arguments `(system, user, json_schema)`.

**Order:**
1. `is_game_creation_request(prompt)` false → `UNSUPPORTED`.
2. **Preset path:** keyword match, as in `spec_from_prompt.match_prompt`. On a match, build the preset with the
   regex overrides and return `OK`, `path="preset"`. This is deterministic and needs no model.
3. **Model path** (when `allow_model` and `complete_json` are set). The system prompt is the constant
   `DRAFT_SYSTEM_PROMPT` below. The user message is the prompt. The schema is `DesignDraft.model_json_schema()`.
   Parse and validate. On `ValidationError` or `JSONDecodeError`, make **one** repair call: append the error list
   (max 1,500 characters) and the previous output, and ask for corrected JSON only. Still invalid → `NEEDS_INPUT` with
   questions built from the errors. A valid draft with `questions` non-empty → `NEEDS_INPUT` with those questions,
   and also the expanded GDS (the UI can show both). Otherwise expand → `OK`, `path="model"`.
4. No model available → `NEEDS_INPUT`: "Which kind of game is this closest to: …" listing the preset titles.

```python
DRAFT_SYSTEM_PROMPT = """You turn a game idea into a JSON object that matches the given schema exactly.
Rules:
- Choose the closest genre and camera. Prefer simple, playable designs a small team could build in a day.
- entities: list what the player meets (pickups, enemies, guards, npcs, doors, hazards, checkpoints, goal). Counts must be small (1-20).
- win: 1-3 conditions the game can check (collect_all, reach_goal, defeat_all, survive_seconds, score_at_least, board_win, match_win).
- lose: conditions such as health_zero or timer_runs_out. Use [] if the player cannot lose.
- custom_rules: at most 3 short sentences for mechanics the lists above cannot express. Leave empty when possible.
- questions: only if the idea is ambiguous in a way that changes the game (max 3).
- title: short, no quotes. Output JSON only."""
```

**`OllamaProvider.complete_json`.** Add it beside `chat_with_tools`, using the same HTTP client and error handling:

```python
    def complete_json(self, model_id: str, system: str, user: str, schema: dict,
                      num_ctx: int = 8192, temperature: float = 0.2, timeout_s: float = 120.0) -> Optional[str]:
        """Structured output via /api/chat `format` (JSON schema). Returns the raw JSON text or None on transport errors."""
        payload = {"model": model_id, "stream": False, "think": False, "format": schema,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "options": {"num_ctx": num_ctx, "temperature": temperature}}
        # POST f"http://{self.host}/api/chat" exactly like chat_with_tools(); return data["message"]["content"]
```

The caller builds `complete_json = lambda s, u, sch: provider.complete_json(get_settings().model_for("design"), s, u, sch)`.

---

## WI-1.7 `design/render.py`

- `render_markdown(gds) -> str`: title, pitch, genre/camera, levels table, an entities table (id, kind, count,
  module), **rules as sentences**, win/lose as sentences, HUD, art/audio one-liners, and the acceptance scenario list.
- `sentence(condition) -> str`, for example: `CountAtLeast(pickup.collected, 5)` → "the player has collected 5 pickups";
  `StatCompare(player.health <= 0)` → "player health drops to 0 or below"; `TimerElapsed(60)` → "60 seconds pass";
  `AllOf` → "all of: …"; `AnyOf` → "any of: …". Effects: `add_stat` → "add 10 to score"; `end_game` →
  "the player wins/loses"; `custom_code` → "custom behaviour: <description>".
- Keep a mapping table in the module (`EVENT_PHRASES`) for every event in `events_catalog`. A unit test checks that
  every catalogue event has a phrase.

---

## WI-1.8 `design/store.py` and `design/legacy.py`

**store.py**
```python
DESIGN_DIR = Path("GameForge") / "design"

def save(project_dir: Path, gds: GameDesignSpec) -> Path:
    """Write game.gds.json and history/r{revision:04d}.gds.json atomically. The revision must exceed the stored one."""

def load(project_dir: Path) -> Optional[GameDesignSpec]: ...
def history(project_dir: Path) -> list[int]: ...
def diff(a: GameDesignSpec, b: GameDesignSpec) -> list[dict]:
    """Structural diff as JSON-Patch-like ops [{"op": "replace", "path": "/entities/2/count", "from": 4, "value": 6}]."""
```
Writes use `tmp` + `os.replace`. Saving revision N when N ≤ the stored revision raises `RevisionConflict`.

**legacy.py** — the bridge to the current pipeline until P6:
```python
def to_legacy_params(gds: GameDesignSpec):
    """Return the legacy recipe params object for a preset-derived GDS, or raise LegacyUnsupported(reason)."""
```
- Genre `grid_board` → `GridBoardParams(project_name, display_title=title, **board.props, plus colours from art.palette[0:3]
  converted from hex to 0–1 RGB tuples)`.
- `platformer` → `PlatformerParams(project_name, display_title, collectible_target=<pickups count>, difficulty, **player.props)`.
- `arena_combat` → `ArenaCombatParams(... **spawner.props, **player.props)`. `card_battler` → `CardBattlerParams(**card_table.props)`.
- `exploration` with level `layout_params` → `ProceduralWorldParams(seed=level.seed, **layout_params)`.
- Anything else raises `LegacyUnsupported("genre X needs the composer (P6)")`.
- Call `params.validate()` before returning.

**Test (`test_gds_legacy.py`):** for each preset, `to_legacy_params(preset())` equals the recipe's default params
(`asdict` comparison, ignoring `project_name` and `display_title`). This is the losslessness proof.

---

## WI-1.9 Tests and the prompt fixture set

`tests/fixtures/gds_prompts.jsonl`: 40 lines `{"prompt": ..., "expect": "preset:<id>" | "model" | "unsupported", "checks": {...}}`.
- 20 preset prompts (4 per legacy genre, varied wording, with parameters: "a 5x5 tic tac toe with 4 in a row vs a
  friend", "platformer with 8 coins called Sky Hop", and so on). `checks` hold the expected overrides.
- 15 model prompts (new genres: "third-person forest adventure collecting 5 relics while avoiding 3 guards",
  "top-down shooter survive 2 minutes", "dungeon crawl with 3 rooms and a key door", …).
- 5 non-game prompts ("fix the build error in Foo.cpp") → `unsupported`.

Tests:
- `test_preset_prompts_deterministic`: all 20 give `status OK`, the right preset and the overrides applied.
- `test_unsupported_prompts`.
- `test_model_path_with_recorded_outputs`: a fake `complete_json` returns recorded drafts from
  `tests/fixtures/gds_model_drafts/*.json` (create 15 by hand). All expand to a valid GDS. One deliberately invalid
  draft triggers exactly one repair call (count calls) and then `NEEDS_INPUT`.
- `test_expand_property`: 500 drafts from a seeded generator (random genre, entities, win/lose combinations within the
  schema) → expansion never raises, or raises only the documented `ExpandError` with a question.

**Live model check (needs Ollama; not a unit test).** `scripts/pipeline/eval_prompt_to_gds.py` runs the 15 model
prompts against `gameforge-qwen3.5-9b` and writes `reports/P1/prompt_to_gds_9b.json`: first-try valid rate, rate after
repair, mean latency, and a fidelity checklist per prompt (does the GDS contain the nouns the prompt mentioned:
relics → pickups, guards → guard entities). **Gate:** ≥ 80 % valid after repair, 100 % of invalid outputs fail closed.
If the 9B misses the gate, record it. That is an expected input to P9, not a reason to change the schema. Mark the
item PARTIAL.

---

## WI-1.10 Wire into the product (legacy pipeline accepts a GDS)

1. `GameTools.plan_game(prompt)` returns `{"status", "gds": gds.model_dump(), "summary_md": render_markdown(gds),
   "questions", "legacy_supported": bool}`.
2. `GameTools.propose_create_game(prompt, session_id)`: build the GDS, then store it in the approval record
   (`args = {"gds": <json>}` instead of recipe params). The approval card renders `summary_md` (collapsed by default,
   expandable).
3. The approved action runs `create_game(gds_json)`: `gds = GameDesignSpec.model_validate_json`; save it with
   `design.store.save(project_dir, gds)` **after** the scaffold stage creates the project dir (add a pipeline hook
   `on_project_dir_ready`); `params = to_legacy_params(gds)`; run the existing `GamePipeline.run(params)`. On
   `LegacyUnsupported`, the approval result is `FAILED` with the reason "This design needs the composer (planned for
   phase 6). Supported today: <preset titles>". Never silently pick a different genre.
4. Approval records created before P1 (with `params`) must still execute: keep a compatibility branch that reads
   `args["params"]`.
5. Design panel (`desktop/panels/design_panel.py`): a read-only Markdown render plus a "JSON" tab with a
   `QPlainTextEdit` and a **Validate** button (`model_validate_json`; errors listed). It is added to the existing rail
   as "Design". The P4 shell replaces it.

**Engine gate:**
`python scripts\pipeline\run_game_pipeline.py --prompt "create a tic tac toe game"` and `... --prompt "make a platformer
with 6 coins"` both go prompt → GDS → legacy params → packaged game, with PASS reports. The project dir contains
`GameForge/design/game.gds.json` (revision 1). Add `--prompt` to the script; keep `--name` working.

## Phase exit gate
1. All unit tests green, and the new tests listed above present.
2. `reports/P1/prompt_to_gds_9b.json` recorded (PASS or PARTIAL with numbers).
3. Two packaged games built from GDS (evidence `reports/P1/legacy_from_gds_{tictactoe,platformer}.json`, copied
   from each project's pipeline report).
4. `context.md`, `docs/00_STATUS.md` (row "Game Design Spec") and this file's Progress table updated.

## Failure cases and prevention
- **Discriminated unions:** serialising conditions without `kind` breaks loading. All condition and effect models set
  `kind` defaults, and the round-trip test covers each type.
- **Model emits extra keys:** `extra="forbid"` rejects them. Do not relax it. The repair call shows the error.
- **Ollama ignores `format`** (older versions): detect a non-JSON reply → repair path → fail closed. Record the
  Ollama version (`/api/version`) in the eval report.
- **Title with quotes** reaching C++ generation: `_safe` blocks it at the schema level, and the legacy recipes
  validate it again.
- **Revision races:** two windows saving the same project raise `RevisionConflict`. The UI asks the user to reload.

## Progress
| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 1.1 | DONE | 2026-10-31T11:20Z | 2026-10-31T11:25Z | `test_events_catalog` (5 passed); MODULE_EVENTS and DEFAULT_MODULE verified |
| 1.2 | DONE | 2026-10-31T11:25Z | 2026-10-31T11:30Z | `test_gds_schema` (10 passed); JSON schema 22 KB; cross-ref validation verified |
| 1.3 | DONE | 2026-10-31T11:32Z | 2026-10-31T11:35Z | `test_draft_schema` (4 passed); DesignDraft JSON schema 3.2 KB <= 6 KB |
| 1.4 | DONE | 2026-10-31T11:38Z | 2026-10-31T11:42Z | `test_gds_expand` (5 passed); deterministic draft -> GDS across genres verified |
| 1.5 | DONE | 2026-10-31T11:45Z | 2026-10-31T11:50Z | `test_gds_presets` (6 passed); 7 legacy presets reproduce recipes losslessly |
| 1.6 | DONE | 2026-10-31T11:55Z | 2026-10-31T12:01Z | prompt_to_gds (9 passed); preset and model draft path with 1 repair attempt |
| 1.7 | DONE | 2026-10-31T12:02Z | 2026-10-31T12:08Z | test_gds_render (4 passed); markdown renderer and full EVENT_PHRASES mapping verified |
| 1.8 | DONE | 2026-10-31T12:09Z | 2026-10-31T12:15Z | test_gds_store (4 passed), test_gds_legacy (2 passed); atomic store and lossless recipe adapter verified |
| 1.9 | DONE | 2026-10-31T12:16Z | 2026-10-31T12:22Z | test_gds_fixtures (4 passed, 500 property drafts PASS); reports/P1/prompt_to_gds_9b.json PASS (100% valid, mean latency 2.16s) |
| 1.10 | TODO | | | |

## Review log (Claude)
_empty_

## Revisions
- 2026-10-31: created (Claude).
