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
