"""Human-readable Markdown renderer and sentence formatters for GameDesignSpec (P1 WI-1.7)."""
from __future__ import annotations

from typing import Union

from .events_catalog import all_events
from .gds import (
    AddStat,
    AllOf,
    AnyOf,
    Condition,
    CountAtLeast,
    CustomCode,
    Effect,
    Emit,
    EndGame,
    EventOccurred,
    GameDesignSpec,
    Message,
    RuleSpec,
    SetStat,
    Spawn,
    StatCompare,
    TimerElapsed,
)

EVENT_PHRASES: dict[str, str] = {
    # Game lifecycle
    "game.started": "the game starts",
    "game.won": "the player wins the game",
    "game.lost": "the player loses the game",
    "game.restarted": "the game restarts",
    "game.paused": "the game is paused",
    "game.resumed": "the game is resumed",
    # Player character
    "player.spawned": "player spawns",
    "player.damaged": "player takes damage",
    "player.died": "player dies",
    "player.respawned": "player respawns",
    "player.jumped": "player jumps",
    "player.dashed": "player dashes",
    "player.sprinted": "player sprints",
    "weapon.switched": "player switches weapon",
    # Pickups & Objectives
    "pickup.collected": "pickup is collected",
    "checkpoint.reached": "checkpoint is reached",
    "lap.completed": "lap is completed",
    "race.finished": "race is finished",
    "goal.reached": "goal is reached",
    "hazard.touched": "hazard is touched",
    # Enemies & Combat
    "enemy.spawned": "enemy spawns",
    "enemy.attacked": "enemy attacks",
    "enemy.killed": "enemy is killed",
    "wave.started": "wave starts",
    "wave.cleared": "wave is cleared",
    "tower.built": "defense tower is built",
    "tower.attacked": "defense tower attacks",
    # Stealth & AI
    "guard.state": "guard changes state",
    "guard.spotted_player": "guard spots player",
    "guard.lost_player": "guard loses sight of player",
    # Dialogue & Quests
    "dialogue.line": "dialogue line spoken",
    "objective.started": "objective starts",
    "objective.updated": "objective is updated",
    "objective.completed": "objective is completed",
    # Bomb site
    "bombsite.planted": "bomb is planted",
    "bombsite.defused": "bomb is defused",
    # Persistence
    "save.loaded": "save game is loaded",
    "save.written": "game is saved",
    # Interactive props
    "interact.used": "interaction used",
    "door.opened": "door opens",
    "door.closed": "door closes",
    "switch.toggled": "switch is toggled",
    "switch.activated": "switch is activated",
    "landmark.discovered": "landmark is discovered",
    # Board games
    "board.move": "board move is played",
    "board.win": "board line is completed (win)",
    "board.lose": "board match is lost",
    "board.warp": "board token warps across tiles",
    "tile.revealed": "board tile is revealed",
    "line.cleared": "matrix line is cleared",
    "board.draw": "board ends in a draw",
    "turn.ended": "turn ends",
    "dice.rolled": "dice is rolled",
    "snake.transition": "player slides down a snake",
    "ladder.transition": "player climbs a ladder",
    # Card games
    "card.played": "card is played",
    "lane.resolved": "lane combat is resolved",
    "match.won": "card match is won",
    "match.lost": "card match is lost",
}


def _fmt_num(n: float | int) -> str:
    if isinstance(n, (int, float)) and n == int(n):
        return str(int(n))
    return str(n)


_STAT_NAMES = {
    "game.score": "the score", "game.time_s": "elapsed time", "player.health": "player health",
    "player.lives": "lives", "player.shield": "player shield", "player.mana": "player mana",
    "player.stamina": "player stamina", "player.ammo": "player ammo", "player.oxygen": "player oxygen",
    "game.gold": "gold", "game.laps": "laps", "game.counter.collected": "collected items",
    "game.counter.waves_cleared": "cleared waves", "game.counter.enemies_killed": "enemies killed",
}


def _stat_name(stat: str) -> str:
    if stat in _STAT_NAMES:
        return _STAT_NAMES[stat]
    parts = stat.split(".")
    if len(parts) == 3 and parts[0] == "entity":
        return f"{parts[1].replace('_', ' ')} {parts[2]}"
    if stat.startswith("game.counter."):
        return stat.split(".", 2)[2].replace("_", " ")
    return stat


def sentence(item: Union[Condition, Effect, RuleSpec]) -> str:
    """Format a Condition, Effect or whole Rule as a natural-language sentence."""
    if isinstance(item, RuleSpec):
        when = EVENT_PHRASES.get(item.when.event, item.when.event)
        if item.when.source:
            when += f" ({item.when.source.replace('_', ' ')})"
        conds = [sentence(c) for c in item.conditions]
        effects = [sentence(e) for e in item.effects]
        text = f"When {when}" + (f" and {' and '.join(conds)}" if conds else "") + f", {'; '.join(effects)}"
        return text[:1].upper() + text[1:]

    if isinstance(item, Message):
        return f'show "{item.text}"'

    if isinstance(item, CountAtLeast):
        if item.event == "pickup.collected":
            return f"the player has collected {item.n} pickups"
        if item.event == "enemy.killed":
            return f"{item.n} enemies are killed"
        phrase = EVENT_PHRASES.get(item.event, item.event)
        return f"{item.n} {phrase} events occur"

    if isinstance(item, StatCompare):
        val_str = _fmt_num(item.value) if isinstance(item.value, (int, float)) else str(item.value)
        if item.stat == "player.health" and item.op == "<=" and item.value <= 0:
            return "player health drops to 0 or below"
        if item.stat.endswith(".remaining") and item.op == "<=" and item.value <= 0:
            parts = item.stat.split(".")
            ent_name = parts[1] if len(parts) > 1 else "target"
            return f"all {ent_name} are defeated"
        if item.op == "<=":
            return f"{_stat_name(item.stat)} drops to {val_str} or below"
        if item.op == ">=":
            return f"{_stat_name(item.stat)} reaches {val_str} or higher"
        if item.op == "==":
            return f"{item.stat} equals {val_str}"
        if item.op == "<":
            return f"{item.stat} falls below {val_str}"
        if item.op == ">":
            return f"{item.stat} exceeds {val_str}"
        return f"{item.stat} {item.op} {val_str}"

    if isinstance(item, TimerElapsed):
        return f"{_fmt_num(item.seconds)} seconds pass"

    if isinstance(item, EventOccurred):
        return EVENT_PHRASES.get(item.event, item.event)

    if isinstance(item, AllOf):
        sub = ", ".join(sentence(sub_item) for sub_item in item.items)
        return f"all of: {sub}"

    if isinstance(item, AnyOf):
        sub = ", ".join(sentence(sub_item) for sub_item in item.items)
        return f"any of: {sub}"

    if isinstance(item, AddStat):
        if item.delta < 0:
            return f"subtract {_fmt_num(-item.delta)} from {_stat_name(item.stat)}"
        return f"add {_fmt_num(item.delta)} to {_stat_name(item.stat)}"

    if isinstance(item, SetStat):
        return f"set {_stat_name(item.stat)} to {_fmt_num(item.value) if isinstance(item.value, (int, float)) else item.value}"

    if isinstance(item, EndGame):
        if item.outcome == "win":
            return "the player wins"
        if item.outcome == "lose":
            return "the player loses"
        return "the game ends in a draw"

    if isinstance(item, CustomCode):
        return f"custom behaviour: {item.description}"

    if isinstance(item, Spawn):
        return f"spawn {item.count} {item.entity_id}"

    if isinstance(item, Emit):
        phrase = EVENT_PHRASES.get(item.event, item.event)
        return f"emit {phrase}"

    return str(item)


def render_markdown(gds: GameDesignSpec) -> str:
    """Renders a GameDesignSpec into a human-readable Markdown document."""
    lines: list[str] = []

    # Title & overview
    lines.append(f"# {gds.meta.title}")
    lines.append("")
    if gds.overview.pitch:
        lines.append(f"> {gds.overview.pitch}")
        lines.append("")
    lines.append(f"- **Genre:** {gds.overview.genre.value}")
    lines.append(f"- **Camera:** {gds.overview.camera.value}")
    lines.append(f"- **Players:** {gds.overview.players} (Multiplayer: {gds.tech.multiplayer})")
    lines.append(f"- **Target Session:** {gds.overview.session_minutes} minutes")
    if getattr(gds.art, "material_theme", "default") != "default":
        lines.append(f"- **Setting:** {gds.art.material_theme} theme, {gds.progression.difficulty} difficulty")
    try:
        from ..kit.runtime_def import describe_objective
        lines.append(f"- **Objective:** {describe_objective(gds)}")
    except Exception:
        pass
    lines.append("")

    # Scene & Levels
    lines.append("## Levels")
    lines.append("")
    lines.append("| Level ID | Size (m) | Layout | Biome | Lighting |")
    lines.append("|---|---|---|---|---|")
    for lvl in gds.scene.levels:
        lines.append(
            f"| `{lvl.level_id}` | {lvl.size_m.x} × {lvl.size_m.y} | {lvl.layout.value} | "
            f"{lvl.biome.value} | {lvl.lighting.value} |"
        )
    lines.append("")

    # Entities
    lines.append("## Entities")
    lines.append("")
    lines.append("| Entity ID | Kind | Count | Module | Placement |")
    lines.append("|---|---|---|---|---|")
    for e in gds.entities:
        placement_str = e.placement.strategy
        if e.placement.slot:
            placement_str += f" ({e.placement.slot})"
        lines.append(f"| `{e.entity_id}` | {e.kind.value} | {e.count} | `{e.module}` | {placement_str} |")
    lines.append("")

    # Goals
    lines.append("## Goals")
    lines.append("")
    if gds.goals.sandbox:
        lines.append("- **Sandbox Mode:** No required win conditions.")
    else:
        lines.append("### Win Conditions")
        for i, cond in enumerate(gds.goals.win, start=1):
            lines.append(f"{i}. {sentence(cond)}")
    lines.append("")

    if gds.goals.lose:
        lines.append("### Lose Conditions")
        for i, cond in enumerate(gds.goals.lose, start=1):
            lines.append(f"{i}. {sentence(cond)}")
        lines.append("")

    # Rules
    if gds.rules:
        lines.append("## Rules")
        lines.append("")
        for r in gds.rules:
            trigger_phrase = EVENT_PHRASES.get(r.when.event, r.when.event)
            src_str = f" from `{r.when.source}`" if r.when.source else ""
            cond_str = f" when {', '.join(sentence(c) for c in r.conditions)}" if r.conditions else ""
            eff_str = ", ".join(sentence(eff) for eff in r.effects)
            lines.append(f"- **{r.rule_id}**: On {trigger_phrase}{src_str}{cond_str} → {eff_str}")
        lines.append("")

    # Architecture
    if getattr(gds, "architecture", None) is not None:
        arch = gds.architecture
        lines.append("## Architecture")
        lines.append("")
        lines.append(f"- **Method:** `{arch.method}`")
        if arch.plan_kind:
            lines.append(f"- **Plan Kind:** `{arch.plan_kind}`")
        if arch.target_classes:
            lines.append(f"- **Target Classes:** {', '.join(f'`{c}`' for c in arch.target_classes)}")
        if arch.target_widgets:
            lines.append(f"- **Target Widgets:** {', '.join(f'`{w}`' for w in arch.target_widgets)}")
        lines.append("")

    # HUD & UI
    if gds.ui.hud:
        lines.append("## User Interface")
        lines.append("")
        lines.append("### HUD Elements")
        for el in gds.ui.hud:
            bind_str = f", bound to `{el.binds}`" if el.binds else ""
            label_str = f" '{el.label}'" if el.label else ""
            lines.append(f"- `{el.element_id}` ({el.kind}){label_str}{bind_str}")
        lines.append("")

    # Art & Audio
    lines.append("## Art & Audio")
    lines.append("")
    palette_str = ", ".join(gds.art.palette)
    lines.append(
        f"- **Art:** Style `{gds.art.style}`, character `{gds.art.character_source}`, "
        f"material theme `{gds.art.material_theme}`, palette: {palette_str}"
    )
    lines.append(
        f"- **Audio:** Music mood `{gds.audio.music_mood}`, ambience `{gds.audio.ambience}`, "
        f"sfx set `{gds.audio.sfx_set}`"
    )
    lines.append("")

    # Acceptance Scenarios
    if gds.acceptance.scenarios:
        lines.append("## Acceptance Scenarios")
        lines.append("")
        for sc in gds.acceptance.scenarios:
            lines.append(f"- `{sc.scenario_id}` (derived from `{sc.derived_from}`, must_pass={sc.must_pass})")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
