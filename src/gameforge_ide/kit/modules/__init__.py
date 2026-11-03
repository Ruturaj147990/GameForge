"""Kit module definitions and schemas (WI-5.14)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from ..registry import KitModule, register


# 1. Player Character
class PlayerCharacterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    move_speed: Optional[float] = Field(None, ge=100.0, le=2000.0)
    player_speed: Optional[float] = Field(None, ge=100.0, le=2000.0)
    jump_velocity: Optional[float] = Field(None, ge=0.0, le=2000.0)
    gravity_scale: Optional[float] = Field(None, ge=0.1, le=10.0)
    air_control: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_health: Optional[float] = Field(None, ge=1.0, le=10000.0)
    player_max_health: Optional[float] = Field(None, ge=1.0, le=10000.0)
    max_stamina: Optional[float] = Field(None, ge=0.0, le=10000.0)
    attack_damage: Optional[float] = Field(None, ge=0.0, le=1000.0)
    player_attack_damage: Optional[float] = Field(None, ge=0.0, le=1000.0)
    attack_range: Optional[float] = Field(None, ge=50.0, le=2000.0)
    player_attack_range: Optional[float] = Field(None, ge=50.0, le=2000.0)
    attack_cooldown: Optional[float] = Field(None, ge=0.05, le=10.0)
    player_attack_cooldown: Optional[float] = Field(None, ge=0.05, le=10.0)
    lives: Optional[int] = Field(0, ge=0, le=99)
    kill_z: Optional[float] = Field(-2000.0, le=0.0)
    attack_mode: Optional[str] = Field("melee")
    weapons: Optional[List[str]] = Field(default_factory=list)


register(
    KitModule(
        module_id="kit.player_character",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeCharacter",
        entity_kinds=frozenset(["player", "character", "hero"]),
        params_model=PlayerCharacterParams,
        property_map={
            "move_speed": "MoveSpeed",
            "jump_velocity": "JumpVelocity",
            "max_health": "MaxHealth",
            "max_stamina": "MaxStamina",
            "attack_damage": "AttackDamage",
            "attack_range": "AttackRange",
            "attack_cooldown": "AttackCooldown",
            "lives": "Lives",
            "kill_z": "KillZ",
        },
        emits=(
            "player.spawned",
            "player.damaged",
            "player.died",
            "player.respawned",
            "player.jumped",
        ),
        automation_tests=("GameForge.Kit.Player",),
        status="PASS",
    )
)


# 2. Pickup
class PickupParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int = Field(1, ge=1, le=1000)
    objective_id: Optional[str] = Field(None, pattern=r"^[a-z][a-z0-9_]{0,39}$")
    respawns: bool = False
    respawn_seconds: float = Field(10.0, ge=1.0, le=600.0)


register(
    KitModule(
        module_id="kit.pickup",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgePickup",
        entity_kinds=frozenset(["pickup", "collectible", "coin", "relic", "key"]),
        params_model=PickupParams,
        property_map={
            "value": "Value",
            "objective_id": "ObjectiveId",
            "respawns": "bRespawns",
            "respawn_seconds": "RespawnSeconds",
        },
        emits=("pickup.collected",),
        automation_tests=("GameForge.Kit.Pickup",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 3. Checkpoint
class CheckpointParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activate_once: bool = True


register(
    KitModule(
        module_id="kit.checkpoint",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeCheckpoint",
        entity_kinds=frozenset(["checkpoint", "respawn_point", "campfire"]),
        params_model=CheckpointParams,
        property_map={"activate_once": "bActivateOnce"},
        emits=("checkpoint.reached",),
        automation_tests=("GameForge.Kit.Checkpoint",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 4. Goal
class GoalParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_stat: Optional[str] = Field(None, pattern=r"^[a-z][a-z0-9_.]*$")
    required_value: float = Field(0.0, ge=0.0)


register(
    KitModule(
        module_id="kit.goal",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeGoal",
        entity_kinds=frozenset(["goal", "portal", "exit", "flag"]),
        params_model=GoalParams,
        property_map={
            "required_stat": "RequiredStat",
            "required_value": "RequiredValue",
        },
        emits=("goal.reached",),
        automation_tests=("GameForge.Kit.Goal",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 5. Hazard
class HazardParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    damage_per_second: float = Field(20.0, ge=0.0, le=10000.0)
    instant_kill: bool = False
    shape_extent: float = Field(100.0, ge=10.0, le=10000.0)


register(
    KitModule(
        module_id="kit.hazard",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeHazard",
        entity_kinds=frozenset(["hazard", "spikes", "lava", "trap", "void"]),
        params_model=HazardParams,
        property_map={
            "damage_per_second": "DamagePerSecond",
            "instant_kill": "bInstantKill",
            "shape_extent": "ShapeExtent",
        },
        emits=("hazard.touched",),
        automation_tests=("GameForge.Kit.Hazard",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 6. Enemy (Melee)
class EnemyMeleeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attack_damage: float = Field(15.0, ge=0.0, le=1000.0)
    attack_range: float = Field(180.0, ge=50.0, le=1000.0)
    attack_cooldown: float = Field(1.0, ge=0.1, le=10.0)
    move_speed: float = Field(350.0, ge=50.0, le=1500.0)
    aggro_range: float = Field(800.0, ge=100.0, le=5000.0)
    max_health: float = Field(50.0, ge=1.0, le=10000.0)


register(
    KitModule(
        module_id="kit.enemy_melee",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeEnemy",
        entity_kinds=frozenset(["enemy", "zombie", "grunt", "monster", "fighter"]),
        params_model=EnemyMeleeParams,
        property_map={
            "attack_damage": "AttackDamage",
            "attack_range": "AttackRange",
            "attack_cooldown": "AttackCooldown",
            "move_speed": "MoveSpeed",
            "aggro_range": "AggroRange",
            "max_health": "MaxHealth",
        },
        emits=("enemy.spawned", "enemy.attacked", "enemy.killed"),
        automation_tests=("GameForge.Kit.Enemy",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 7. Enemy (Ranged)
class EnemyRangedParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attack_damage: float = Field(10.0, ge=0.0, le=1000.0)
    attack_range: float = Field(900.0, ge=200.0, le=5000.0)
    attack_cooldown: float = Field(1.5, ge=0.1, le=10.0)
    move_speed: float = Field(280.0, ge=50.0, le=1500.0)
    aggro_range: float = Field(1200.0, ge=200.0, le=6000.0)
    projectile_speed: float = Field(1500.0, ge=200.0, le=10000.0)
    max_health: float = Field(35.0, ge=1.0, le=10000.0)


register(
    KitModule(
        module_id="kit.enemy_ranged",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeEnemy",
        entity_kinds=frozenset(["archer", "turret", "sniper", "mage"]),
        params_model=EnemyRangedParams,
        property_map={
            "attack_damage": "AttackDamage",
            "attack_range": "AttackRange",
            "attack_cooldown": "AttackCooldown",
            "move_speed": "MoveSpeed",
            "aggro_range": "AggroRange",
            "projectile_speed": "ProjectileSpeed",
            "max_health": "MaxHealth",
        },
        emits=("enemy.spawned", "enemy.attacked", "enemy.killed"),
        automation_tests=("GameForge.Kit.Enemy",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 8. Spawner
class SpawnerParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enemy_entity_id: str = Field("enemy", pattern=r"^[a-z][a-z0-9_]{0,39}$")
    wave_count: int = Field(3, ge=1, le=50)
    enemies_per_wave: int = Field(3, ge=1, le=50)
    seconds_between_waves: float = Field(5.0, ge=0.5, le=120.0)
    spawn_radius: float = Field(400.0, ge=50.0, le=2000.0)
    # Optional preset overrides
    enemy_max_health: Optional[float] = None
    enemy_attack_damage: Optional[float] = None
    enemy_attack_range: Optional[float] = None
    enemy_attack_cooldown: Optional[float] = None
    enemy_speed: Optional[float] = None


register(
    KitModule(
        module_id="kit.spawner",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeSpawner",
        entity_kinds=frozenset(["spawner", "wave_spawner", "nest"]),
        params_model=SpawnerParams,
        property_map={
            "enemy_entity_id": "EnemyEntityId",
            "wave_count": "WaveCount",
            "enemies_per_wave": "EnemiesPerWave",
            "seconds_between_waves": "SecondsBetweenWaves",
            "spawn_radius": "SpawnRadius",
        },
        emits=("wave.started", "wave.cleared"),
        automation_tests=("GameForge.Kit.Spawner",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 9. Guard
class GuardParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patrol_radius: float = Field(1000.0, ge=100.0, le=10000.0)
    aggro_radius: float = Field(600.0, ge=100.0, le=5000.0)
    move_speed: float = Field(300.0, ge=50.0, le=1200.0)


register(
    KitModule(
        module_id="kit.guard",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeGuard",
        entity_kinds=frozenset(["guard", "patrol", "sentry"]),
        params_model=GuardParams,
        property_map={
            "patrol_radius": "PatrolRadius",
            "aggro_radius": "AggroRadius",
            "move_speed": "MoveSpeed",
        },
        emits=("guard.state", "guard.spotted_player", "guard.lost_player"),
        automation_tests=("GameForge.Kit.Guard",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 10. Quest Giver
class QuestGiverParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective_id: str = Field("relics", pattern=r"^[a-z][a-z0-9_]{0,39}$")
    objective_title: str = Field("Recover relics", max_length=100)
    objective_target: int = Field(3, ge=1, le=100)
    talk_on_overlap: bool = True


register(
    KitModule(
        module_id="kit.quest_giver",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeQuestGiver",
        entity_kinds=frozenset(["quest_giver", "npc", "guide"]),
        params_model=QuestGiverParams,
        property_map={
            "objective_id": "ObjectiveId",
            "objective_title": "ObjectiveTitle",
            "objective_target": "ObjectiveTarget",
            "talk_on_overlap": "bTalkOnOverlap",
        },
        emits=("dialogue.line",),
        automation_tests=("GameForge.Kit.QuestGiver",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 11. Objective
class ObjectiveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective_id: str = Field("main_objective", pattern=r"^[a-z][a-z0-9_]{0,39}$")
    target_count: int = Field(1, ge=1, le=1000)
    auto_start: bool = True


register(
    KitModule(
        module_id="kit.objective",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeObjectiveSubsystem",
        entity_kinds=frozenset(["objective", "mission", "task"]),
        params_model=ObjectiveParams,
        property_map={
            "objective_id": "ObjectiveId",
            "target_count": "TargetCount",
            "auto_start": "bAutoStart",
        },
        emits=(
            "objective.started",
            "objective.updated",
            "objective.completed",
            "save.loaded",
            "save.written",
        ),
        automation_tests=("GameForge.Kit.Objectives",),
        status="PASS",
    )
)


# 12. Door
class DoorParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_stat: Optional[str] = Field(None, pattern=r"^[a-z][a-z0-9_.]*$")
    required_value: float = Field(1.0, ge=0.0)
    open_seconds: float = Field(1.0, ge=0.1, le=30.0)


register(
    KitModule(
        module_id="kit.door",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeDoor",
        entity_kinds=frozenset(["door", "gate", "barrier"]),
        params_model=DoorParams,
        property_map={
            "required_stat": "RequiredStat",
            "required_value": "RequiredValue",
            "open_seconds": "Seconds",
        },
        emits=("interact.used", "door.opened", "door.closed"),
        automation_tests=("GameForge.Kit.Door",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 13. Switch
class SwitchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_tag: str = Field("", max_length=64)
    toggle: bool = False


register(
    KitModule(
        module_id="kit.switch",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeSwitch",
        entity_kinds=frozenset(["switch", "lever", "button"]),
        params_model=SwitchParams,
        property_map={"target_tag": "TargetTag", "toggle": "bToggle"},
        emits=("interact.used", "switch.toggled"),
        automation_tests=("GameForge.Kit.Switch",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 14. Moving Platform
class MovingPlatformParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    end_offset_x: float = 0.0
    end_offset_y: float = 0.0
    end_offset_z: float = 0.0
    seconds: float = Field(3.0, ge=0.5, le=60.0)
    pause_seconds: float = Field(1.0, ge=0.0, le=10.0)


register(
    KitModule(
        module_id="kit.moving_platform",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeMovingPlatform",
        entity_kinds=frozenset(["moving_platform", "elevator", "lift", "floating_pad"]),
        params_model=MovingPlatformParams,
        property_map={
            "end_offset_x": "EndOffsetX",
            "end_offset_y": "EndOffsetY",
            "end_offset_z": "EndOffsetZ",
            "seconds": "Seconds",
            "pause_seconds": "PauseSeconds",
        },
        emits=(),
        automation_tests=("GameForge.Kit.MovingPlatform",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 15. Landmark
class LandmarkParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    discover_radius: float = Field(500.0, ge=50.0, le=10000.0)


register(
    KitModule(
        module_id="kit.landmark",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeLandmark",
        entity_kinds=frozenset(["landmark", "tower", "statue", "ruins", "monument"]),
        params_model=LandmarkParams,
        property_map={"discover_radius": "DiscoverRadius"},
        emits=("landmark.discovered",),
        automation_tests=("GameForge.Kit.Landmark",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 16. Prop
class PropParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mesh_path: str = Field("/Engine/BasicShapes/Cube.Cube", max_length=256)
    scale_x: float = Field(1.0, ge=0.01, le=100.0)
    scale_y: float = Field(1.0, ge=0.01, le=100.0)
    scale_z: float = Field(1.0, ge=0.01, le=100.0)


register(
    KitModule(
        module_id="kit.prop",
        version="2.0.0",
        runtime_class="/Script/Engine.StaticMeshActor",
        entity_kinds=frozenset(["prop", "rock", "tree", "barrel", "crate", "furniture"]),
        params_model=PropParams,
        property_map={
            "mesh_path": "StaticMesh",
        },
        emits=(),
        automation_tests=(),
        status="PASS",
    )
)


# 17. Grid Board
class GridBoardParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    board_size: int = Field(3, ge=3, le=100)
    win_length: Optional[int] = Field(3, ge=1, le=100)
    gravity: bool = False
    vs_ai: bool = True
    ai_level: str = Field("random", pattern=r"^(random|greedy|minimax|perfect)$")
    cell_size_cm: float = Field(120.0, ge=20.0, le=1000.0)
    snakes: Optional[int] = Field(None, ge=0, le=100)
    ladders: Optional[int] = Field(None, ge=0, le=100)
    dice_sides: Optional[int] = Field(None, ge=1, le=100)
    players: Optional[int] = Field(None, ge=1, le=8)


register(
    KitModule(
        module_id="kit.grid_board",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeGridBoard",
        entity_kinds=frozenset(["board", "grid", "tictactoe", "connect_four", "gomoku", "snakes_and_ladders", "board_game"]),
        params_model=GridBoardParams,
        property_map={
            "board_size": "BoardSize",
            "win_length": "WinLength",
            "gravity": "bGravity",
            "vs_ai": "bVsAI",
            "cell_size_cm": "CellSizeCm",
            "snakes": "Snakes",
            "ladders": "Ladders",
            "dice_sides": "DiceSides",
            "players": "Players",
        },
        emits=("board.move", "board.win", "board.draw", "turn.ended"),
        automation_tests=("GameForge.Kit.GridBoard",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)


# 18. Card Match
class CardMatchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deck_size: Optional[int] = Field(20, ge=5, le=100)
    hand_size: Optional[int] = Field(4, ge=1, le=10)
    energy_per_turn: Optional[int] = Field(3, ge=1, le=10)
    # Preset fields
    player_base_health: Optional[int] = Field(30, ge=1, le=1000)
    opponent_base_health: Optional[int] = Field(30, ge=1, le=1000)
    starting_hand_size: Optional[int] = Field(4, ge=1, le=10)
    max_hand_size: Optional[int] = Field(7, ge=1, le=20)
    base_energy_per_turn: Optional[int] = Field(3, ge=1, le=10)
    lane_count: Optional[int] = Field(3, ge=1, le=10)


register(
    KitModule(
        module_id="kit.card_match",
        version="2.0.0",
        runtime_class="/Script/GameForgeRuntime.GameForgeCardTable",
        entity_kinds=frozenset(["card_table", "deck", "arena_cards", "card_match"]),
        params_model=CardMatchParams,
        property_map={
            "deck_size": "DeckSize",
            "hand_size": "HandSize",
            "energy_per_turn": "EnergyPerTurn",
        },
        emits=("card.played", "turn.ended", "lane.resolved", "match.won", "match.lost"),
        automation_tests=("GameForge.Kit.CardMatch",),
        status="PASS",
        evidence=("reports/P5/kit_scenarios_final.json",),
    )
)
