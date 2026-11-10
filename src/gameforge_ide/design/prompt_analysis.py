"""Deterministic & open-vocabulary prompt analysis: extracts every concrete fact a game prompt states.

Turns any arbitrary user prompt into a rich PromptBrief — genre, spatial/gameplay archetype, camera,
theme, open-vocabulary named enemies / collectibles / interactive switches / doors / hazards with counts,
weapons, mechanics, dynamic resources (oxygen, shield, mana, stamina, ammo, gold), win/lose conditions,
and synthesized custom rules.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .draft import DesignDraft, DraftEntity, DraftLose, DraftWin
from .gds import Biome, CameraKind, EntityKind, Genre, Lighting

_NUMBER_WORDS = {
    "one": 1, "single": 1, "two": 2, "couple": 2, "pair": 2, "three": 3, "few": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "dozen": 12,
    "fifteen": 15, "twenty": 20, "thirty": 30, "fifty": 50, "several": 4, "many": 8, "lots": 10, "hundred": 100,
}
_NUM = r"(\d{1,4}|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")"

ENEMY_NOUNS: Dict[str, Tuple[str, bool, str]] = {
    "zombie": ("Zombie", False, "#5E8C3A"), "skeleton": ("Skeleton", False, "#D8D2C0"),
    "goblin": ("Goblin", False, "#4F8A2E"), "orc": ("Orc", False, "#3F6B2A"), "troll": ("Troll", False, "#6B7F5A"),
    "robot": ("Robot", False, "#8A949E"), "drone": ("Drone", True, "#5A6E80"), "alien": ("Alien", True, "#6FD13B"),
    "invader": ("Invader", True, "#9B5DE5"), "monster": ("Monster", False, "#8E2C48"), "demon": ("Demon", False, "#A3201B"),
    "ghost": ("Ghost", False, "#C9E4F2"), "vampire": ("Vampire", False, "#5C0F1E"), "werewolf": ("Werewolf", False, "#5A4632"),
    "spider": ("Spider", False, "#2B2B2B"), "slime": ("Slime", False, "#5BD16B"), "bat": ("Bat", False, "#3A2E3F"),
    "wolf": ("Wolf", False, "#6E6E6E"), "bandit": ("Bandit", False, "#7A4E2D"), "pirate": ("Pirate", False, "#7B3F2A"),
    "soldier": ("Soldier", True, "#556B2F"), "terrorist": ("Hostile Operative", True, "#6B5A3C"), "mercenary": ("Mercenary", True, "#4A4A3A"),
    "knight": ("Knight", False, "#A9A9B8"), "ninja": ("Ninja", False, "#1E1E26"), "samurai": ("Samurai", False, "#8C1C13"),
    "archer": ("Archer", True, "#7D8C3A"), "wizard": ("Wizard", True, "#4B3B8F"), "witch": ("Witch", True, "#3B2A5A"),
    "mage": ("Mage", True, "#4C3FA3"), "sorcerer": ("Sorcerer", True, "#5A2E8C"), "turret": ("Turret", True, "#707A84"),
    "cultist": ("Cultist", False, "#4A1F3D"), "mutant": ("Mutant", False, "#7FA13A"), "beast": ("Beast", False, "#6B3E26"),
    "insect": ("Insect", False, "#3E5C1F"), "bug": ("Bug", False, "#466B1F"), "rat": ("Rat", False, "#5E544C"),
    "enemy": ("Enemy", False, "#C0392B"), "foe": ("Foe", False, "#C0392B"), "minion": ("Minion", False, "#B5563A"),
    "creep": ("Creep", False, "#B5563A"), "boss": ("Boss", False, "#7D0A0A"), "dragon": ("Dragon", True, "#A01818"),
    "shooter": ("Gunner", True, "#5D6D7E"), "gunner": ("Gunner", True, "#5D6D7E"), "sniper": ("Sniper", True, "#3D4B3A"),
    "tank": ("Tank", True, "#59614A"), "mummy": ("Mummy", False, "#C2B280"), "golem": ("Golem", False, "#7D7468"),
    "yeti": ("Yeti", False, "#E8F0F5"), "shark": ("Shark", False, "#5C7A8C"), "crab": ("Crab", False, "#C0482B"),
    "elemental": ("Elemental", True, "#E86A17"), "leviathan": ("Leviathan", False, "#1A5276"),
    "mech": ("Mech", True, "#566573"), "crawler": ("Crawler", False, "#6C3483"), "sandworm": ("Sandworm", False, "#B9770E"),
    "sentinel": ("Sentinel", True, "#2E86C1"), "specter": ("Specter", False, "#85C1E9"), "wraith": ("Wraith", False, "#4A235A"),
    "gargoyle": ("Gargoyle", False, "#616A6B"), "hound": ("Hound", False, "#784212"), "automaton": ("Automaton", True, "#909497"),
    "stalker": ("Stalker", False, "#2C3E50"), "wyvern": ("Wyvern", True, "#922B21"), "anglerfish": ("Anglerfish", False, "#1B4F72"),
    "necromancer": ("Necromancer", True, "#6A1B9A"), "assassin": ("Assassin", False, "#212121"),
    "lich": ("Lich", True, "#4A148C"), "beholder": ("Beholder", True, "#D81B60"),
    "spectre": ("Spectre", False, "#85C1E9"), "archon": ("Archon", True, "#7B1FA2"),
}
COLLECTIBLE_NOUNS: Dict[str, Tuple[str, str]] = {
    "coin": ("Coin", "#F2C230"), "gem": ("Gem", "#2EE6D6"), "jewel": ("Jewel", "#E0115F"), "diamond": ("Diamond", "#B9F2FF"),
    "crystal": ("Crystal", "#7FDBFF"), "relic": ("Relic", "#B57EDC"), "artifact": ("Artifact", "#D4A017"),
    "star": ("Star", "#FFE14D"), "orb": ("Orb", "#7A5CFF"), "key": ("Key", "#FFD700"), "treasure": ("Treasure", "#E1AD21"),
    "chest": ("Chest", "#9C6B30"), "battery": ("Battery", "#4CFF7A"), "cell": ("Energy Cell", "#4CFF7A"),
    "core": ("Core", "#00E5FF"), "shard": ("Shard", "#9AE6FF"), "fragment": ("Fragment", "#C9A0FF"),
    "mushroom": ("Mushroom", "#E2412D"), "flower": ("Flower", "#FF7EB6"), "apple": ("Apple", "#D62828"),
    "fruit": ("Fruit", "#FF8C1A"), "egg": ("Egg", "#F5E6C8"), "feather": ("Feather", "#E8E8F0"), "pearl": ("Pearl", "#F4F1EA"),
    "ring": ("Ring", "#F5C542"), "token": ("Token", "#F2B134"), "medal": ("Medal", "#D4AF37"), "trophy": ("Trophy", "#D4AF37"),
    "scroll": ("Scroll", "#E8D8A8"), "potion": ("Potion", "#E04FBF"), "rune": ("Rune", "#6E8BFF"), "idol": ("Idol", "#C8A951"),
    "skull": ("Skull", "#E8E3D3"), "ore": ("Ore", "#B87333"), "fuel": ("Fuel Canister", "#FF6A00"), "part": ("Part", "#9FA8B0"),
    "sample": ("Sample", "#7CFC00"), "package": ("Package", "#B5835A"), "letter": ("Letter", "#F3E9D2"),
    "candy": ("Candy", "#FF5DA2"), "cookie": ("Cookie", "#C68E50"), "pickup": ("Pickup", "#F2C230"),
    "collectible": ("Collectible", "#F2C230"), "item": ("Item", "#F2C230"), "loot": ("Loot", "#E1AD21"),
    "canister": ("Canister", "#00E5FF"), "black box": ("Black Box", "#FF9F1C"), "black-box": ("Black Box", "#FF9F1C"),
    "chip": ("Data Chip", "#00F5D4"), "sigil": ("Sigil", "#9B5DE5"), "blueprint": ("Blueprint", "#4CC9F0"),
    "bloodstone": ("Bloodstone", "#C62828"), "tome": ("Tome", "#5D4037"), "chalice": ("Chalice", "#FFD700"),
    "urn": ("Urn", "#B0BEC5"), "soul": ("Soul", "#00E5FF"),
}
HAZARD_NOUNS: Dict[str, str] = {
    "lava": "Lava", "spike": "Spikes", "trap": "Trap", "acid": "Acid", "fire": "Fire", "flame": "Flames",
    "poison": "Poison", "laser": "Laser", "pit": "Pit", "saw": "Saw", "mine": "Mine", "electric": "Electric Floor",
    "quicksand": "Quicksand", "thorn": "Thorns", "toxic": "Toxic Waste", "radiation": "Radiation",
    "vent": "Thermal Vent", "geyser": "Steam Geyser", "meteor": "Meteor Shower", "crusher": "Crusher",
}
SWITCH_NOUNS: Dict[str, str] = {
    "terminal": "Security Terminal", "console": "Control Console", "switch": "Power Switch",
    "lever": "Mechanism Lever", "relay": "Power Relay", "valve": "Pressure Valve",
    "brazier": "Ritual Brazier", "generator": "Generator", "pylon": "Energy Pylon",
    "panel": "Access Panel", "anvil": "Forge Anvil", "node": "Data Node",
}
WEAPON_NOUNS: Dict[str, Tuple[str, bool]] = {
    "shotgun": ("Shotgun", True), "rifle": ("Rifle", True), "pistol": ("Pistol", True), "revolver": ("Revolver", True),
    "smg": ("SMG", True), "sniper": ("Sniper Rifle", True), "laser": ("Laser Blaster", True), "plasma": ("Plasma Rifle", True),
    "rocket": ("Rocket Launcher", True), "blaster": ("Blaster", True), "bow": ("Bow", True), "crossbow": ("Crossbow", True),
    "fireball": ("Fireball Staff", True), "wand": ("Magic Wand", True), "staff": ("Arcane Staff", True),
    "harpoon": ("Harpoon Launcher", True), "railgun": ("Railgun", True), "cannon": ("Pulse Cannon", True),
    "sword": ("Sword", False), "katana": ("Katana", False), "blade": ("Blade", False), "axe": ("Battle Axe", False),
    "hammer": ("Warhammer", False), "dagger": ("Dagger", False), "spear": ("Spear", False), "club": ("Club", False),
    "scythe": ("Scythe", False), "gauntlet": ("Gauntlet", False),
}
GOAL_PHRASES = re.compile(
    r"\b(reach|get to|find|escape (?:through|via|to)|make it to|arrive at|enter|exit through|go to|head to|return to|deliver .*? to)\s+"
    r"(?:the\s+)?(exit|portal|door|gate|flag|finish(?: line)?|goal|summit|top|castle|temple|ship|rocket|helicopter|"
    r"tower|cave|end|beacon|lighthouse|altar|throne|spaceship|escape pod|extraction(?: point)?|boat|submarine|vault|bay|sanctuary)\b",
    re.I,
)
ESCAPE = re.compile(r"\b(escape|get out|break out|flee|extract)\b", re.I)

THEMES: Dict[str, Dict[str, Any]] = {
    "volcano": {"kw": ("volcano", "volcanic", "lava", "magma", "inferno", "hell", "molten"), "biome": Biome.MOUNTAIN,
                "lighting": Lighting.DUSK, "palette": ["#2B1B17", "#E25822", "#FFB347", "#5C1A0B"],
                "music": "tense", "ambience": "wind"},
    "ice": {"kw": ("ice", "icy", "snow", "snowy", "frozen", "arctic", "glacier", "winter", "tundra", "polar"),
            "biome": Biome.MOUNTAIN, "lighting": Lighting.DAY, "palette": ["#DCEBF5", "#7FB3D5", "#2E86C1", "#F4F6F7"],
            "music": "calm", "ambience": "wind"},
    "snow_ice": {"kw": ("snow_ice", "blizzard", "iceberg", "frostbite"),
                 "biome": Biome.MOUNTAIN, "lighting": Lighting.DAY, "palette": ["#DCEBF5", "#7FB3D5", "#2E86C1", "#F4F6F7"],
                 "music": "calm", "ambience": "wind"},
    "desert": {"kw": ("desert", "sand", "sandy", "dune", "dunes", "pyramid", "egypt", "egyptian", "oasis", "canyon",
                      "wild west", "western", "cowboy"),
               "biome": Biome.DESERT, "lighting": Lighting.DAY, "palette": ["#E8C07D", "#C2703D", "#7A4A2A", "#F6E3B4"],
               "music": "heroic", "ambience": "wind"},
    "desert_sand": {"kw": ("desert_sand", "sahara", "badlands", "mesa"),
                    "biome": Biome.DESERT, "lighting": Lighting.DAY, "palette": ["#E8C07D", "#C2703D", "#7A4A2A", "#F6E3B4"],
                    "music": "heroic", "ambience": "wind"},
    "forest": {"kw": ("forest", "woods", "woodland", "jungle", "grove", "swamp", "enchanted", "fairy", "elf", "elven",
                      "druid", "garden", "meadow"),
               "biome": Biome.FOREST, "lighting": Lighting.DAY, "palette": ["#2D5A27", "#6A994E", "#A7C957", "#6B4226"],
               "music": "calm", "ambience": "forest"},
    "island": {"kw": ("island", "beach", "tropical", "pirate", "ocean", "sea", "coast", "lagoon"),
               "biome": Biome.ISLAND, "lighting": Lighting.DAY, "palette": ["#F4E1B0", "#2EC4B6", "#0B7A75", "#3A7D44"],
               "music": "playful", "ambience": "wind"},
    "space": {"kw": ("space", "spaceship", "space station", "orbital", "galaxy", "planet", "mars", "moon", "asteroid", "alien",
                     "cosmic", "starship", "orbit"),
              "biome": Biome.NONE, "lighting": Lighting.NIGHT, "palette": ["#0B0C2A", "#3A0CA3", "#4CC9F0", "#F72585"],
              "music": "tense", "ambience": "none"},
    "cyber": {"kw": ("cyber", "cyberpunk", "neon", "synthwave", "hacker", "futuristic", "sci-fi", "scifi", "robot",
                     "tech", "laboratory", "lab", "facility", "server"),
              "biome": Biome.INDOOR, "lighting": Lighting.NIGHT, "palette": ["#14002E", "#00F5D4", "#F15BB5", "#3A0CA3"],
              "music": "tense", "ambience": "city"},
    "scifi_metal": {"kw": ("scifi_metal", "hangar", "mech bay", "reactor"),
                    "biome": Biome.INDOOR, "lighting": Lighting.INDOOR, "palette": ["#33373D", "#6C7A89", "#00D2FF", "#FF8C00"],
                    "music": "tense", "ambience": "city"},
    "dungeon": {"kw": ("dungeon", "crypt", "catacomb", "tomb", "cave", "cavern", "mine", "underground", "sewer",
                       "labyrinth", "maze", "vault", "keep", "stronghold"),
                "biome": Biome.DUNGEON, "lighting": Lighting.INDOOR, "palette": ["#2E2A27", "#6D5D4B", "#C8A165", "#4A3B2C"],
                "music": "tense", "ambience": "dungeon"},
    "gothic_crypt": {"kw": ("gothic", "crypt", "catacomb", "dark fantasy", "necromancer", "undead", "bloodstone"),
                     "biome": Biome.DUNGEON, "lighting": Lighting.NIGHT, "palette": ["#1A162B", "#4A3E5C", "#8E44AD", "#C39BD3"],
                     "music": "tense", "ambience": "dungeon"},
    "haunted": {"kw": ("haunted", "spooky", "horror", "creepy", "graveyard", "cemetery", "halloween", "ghost", "vampire"),
                "biome": Biome.DUNGEON, "lighting": Lighting.NIGHT, "palette": ["#1B1B2F", "#5B5F97", "#B8B8D1", "#7D3C98"],
                "music": "tense", "ambience": "forest"},
    "castle": {"kw": ("castle", "medieval", "kingdom", "knight", "fortress", "keep", "citadel", "royal", "monastery"),
               "biome": Biome.MOUNTAIN, "lighting": Lighting.DAY, "palette": ["#8D8D8D", "#4F5D75", "#BFC0C0", "#A4161A"],
               "music": "heroic", "ambience": "wind"},
    "stone_wood": {"kw": ("stone_wood", "tavern", "courtyard", "cobblestone", "blacksmith"),
                   "biome": Biome.MOUNTAIN, "lighting": Lighting.DAY, "palette": ["#6B6560", "#8A7F74", "#D4A017", "#5DADE2"],
                   "music": "heroic", "ambience": "wind"},
    "city": {"kw": ("city", "urban", "street", "rooftop", "downtown", "metro", "subway", "town", "village"),
             "biome": Biome.NONE, "lighting": Lighting.DUSK, "palette": ["#3D405B", "#81B29A", "#F2CC8F", "#E07A5F"],
             "music": "heroic", "ambience": "city"},
    "candy": {"kw": ("candy", "sweet", "dessert", "cake", "cartoon", "cute", "toy", "toys", "kids"),
              "biome": Biome.NONE, "lighting": Lighting.DAY, "palette": ["#FFC8DD", "#BDE0FE", "#FFAFCC", "#A2D2FF"],
              "music": "playful", "ambience": "none"},
    "toon_flat": {"kw": ("toon_flat", "cel shaded", "flat shaded"),
                  "biome": Biome.NONE, "lighting": Lighting.DAY, "palette": ["#7CC66B", "#F2E3C6", "#9B5DE5", "#FF6B6B"],
                  "music": "playful", "ambience": "none"},
    "ocean": {"kw": ("underwater", "aquatic", "reef", "deep sea", "deep-sea", "atlantis", "submarine", "submersible", "sunken"),
              "biome": Biome.ISLAND, "lighting": Lighting.DUSK, "palette": ["#03045E", "#0077B6", "#00B4D8", "#90E0EF"],
              "music": "calm", "ambience": "none"},
    "default": {"kw": (), "biome": Biome.NONE, "lighting": Lighting.DAY,
                "palette": ["#2E3440", "#88C0D0", "#EBCB8B", "#BF616A"], "music": "none", "ambience": "none"},
}

GENRE_KEYWORDS: List[Tuple[Genre, Tuple[str, ...], float]] = [
    (Genre.ARENA_COMBAT, ("bomb defusal", "defuse the bomb", "plant the bomb",
                          "tactical shooter", "tower defense", "defend the base", "defend the core",
                          "turret defense", "lane defense", "wave survival", "horde survival"), 4.0),
    (Genre.PLATFORMER, ("racing", "race", "racer", "kart", "time trial", "speedrun", "runner", "endless runner", "hoverbike"), 2.2),
    (Genre.GRID_BOARD, ("chess", "checkers", "draughts", "tic tac toe", "tic-tac-toe", "connect four", "connect 4",
                        "board game", "gomoku", "othello", "reversi", "roll and move", "dice board"), 3.0),
    (Genre.CARD_BATTLER, ("card", "cards", "deck", "deckbuilder", "deck builder", "hand of cards", "tcg", "ccg"), 3.0),
    (Genre.PUZZLE, ("puzzle", "sudoku", "match three", "match-3", "tetris", "minesweeper", "sokoban", "logic"), 2.5),
    (Genre.PLATFORMER, ("platformer", "platform", "platforms", "jump", "jumping", "parkour", "obby", "obstacle course",
                        "side-scroller", "side scroller", "sidescroller", "climb", "double jump"), 2.0),
    (Genre.TOP_DOWN_SHOOTER, ("top-down shooter", "top down shooter", "twin stick", "twin-stick", "bullet hell",
                              "shmup", "shoot em up", "shoot 'em up"), 3.0),
    (Genre.ARENA_COMBAT, ("arena", "wave", "waves", "horde", "survive", "survival", "gladiator", "brawler", "beat em up",
                          "hack and slash", "hack-and-slash", "fight", "fighting", "combat", "battle", "defend",
                          "shooter", "shoot", "shooting", "fps", "gun", "guns"), 1.2),
    (Genre.DUNGEON_CRAWLER, ("dungeon", "crawler", "roguelike", "rogue-like", "roguelite", "crypt", "catacomb",
                             "labyrinth", "maze", "rooms", "heist", "infiltrate", "infiltration"), 2.0),
    (Genre.EXPLORATION, ("explore", "exploration", "open world", "open-world", "wander", "discover", "adventure",
                         "landscape", "hike", "hiking", "sandbox", "salvage", "submersible", "submarine"), 1.5),
    (Genre.ACTION_ADVENTURE, ("quest", "rpg", "hero", "villager", "npc", "kingdom", "story"), 1.0),
]

CAMERA_PATTERNS: List[Tuple[CameraKind, re.Pattern]] = [
    (CameraKind.FIRST_PERSON, re.compile(r"\b(first[- ]person|fps|1st[- ]person)\b", re.I)),
    (CameraKind.TOP_DOWN, re.compile(r"\b(top[- ]down|topdown|bird'?s[- ]eye|isometric|twin[- ]stick|overhead|tower\s+defense)\b", re.I)),
    (CameraKind.SIDE_SCROLLER, re.compile(r"\b(side[- ]?scroll(?:er|ing)?|2d platformer|2\.5d|metroidvania)\b", re.I)),
    (CameraKind.THIRD_PERSON, re.compile(r"\b(third[- ]person|3rd[- ]person|over the shoulder)\b", re.I)),
]

_STOP_TITLE = {"a", "an", "the", "game", "make", "create", "build", "me", "please", "i", "want", "where", "with", "and",
               "of", "in", "on", "to", "for", "that", "which", "you", "player", "players", "simple", "fun", "cool",
               "awesome", "small", "big", "3d", "2d", "new", "my", "some", "who", "must", "can", "has", "have",
               "design", "generate", "develop", "craft"}


@dataclass
class NamedThing:
    noun: str
    label: str
    count: Optional[int] = None
    color: str = "#C0392B"
    ranged: bool = False
    boss: bool = False


@dataclass
class PromptBrief:
    prompt: str
    title: Optional[str] = None
    genre: Optional[Genre] = None
    game_subtype: Optional[str] = None
    genre_scores: Dict[str, float] = field(default_factory=dict)
    camera: Optional[CameraKind] = None
    camera_explicit: bool = False
    theme: Optional[str] = None
    biome: Biome = Biome.NONE
    lighting: Optional[Lighting] = None
    palette: List[str] = field(default_factory=list)
    music_mood: str = "none"
    ambience: str = "none"
    art_style: Optional[str] = None
    enemies: List[NamedThing] = field(default_factory=list)
    collectibles: List[NamedThing] = field(default_factory=list)
    switches: List[NamedThing] = field(default_factory=list)
    hazards: List[str] = field(default_factory=list)
    weapons: List[str] = field(default_factory=list)
    mechanics: List[str] = field(default_factory=list)
    goal_target: Optional[str] = None
    wants_goal: bool = False
    has_guards: bool = False
    has_npc: bool = False
    has_doors: bool = False
    has_checkpoints: bool = False
    has_moving_platforms: bool = False
    waves: Optional[int] = None
    laps: Optional[int] = None
    checkpoints: Optional[int] = None
    boss_phases: Optional[int] = None
    survive_seconds: Optional[int] = None
    time_limit_seconds: Optional[int] = None
    score_target: Optional[int] = None
    lives: Optional[int] = None
    player_health: Optional[int] = None
    difficulty: Optional[str] = None
    level_size: Optional[str] = None
    ranged_player: Optional[bool] = None
    double_jump: bool = False
    sprint: bool = False
    players: int = 1
    player_abilities: List[str] = field(default_factory=list)
    ability_key_binds: Dict[str, str] = field(default_factory=dict)
    boss_name: Optional[str] = None
    key_pickups: int = 0
    interactive_doors: int = 0
    custom_rules: List[str] = field(default_factory=list)
    unsupported: List[str] = field(default_factory=list)
    mechanics_notes: List[str] = field(default_factory=list)

    @property
    def is_board_like(self) -> bool:
        return self.genre in (Genre.GRID_BOARD, Genre.CARD_BATTLER, Genre.PUZZLE)

    def summary_lines(self) -> List[str]:
        out: List[str] = []
        if self.title:
            out.append(f"title: {self.title}")
        if self.genre:
            out.append(f"genre: {self.genre.value}")
        if self.game_subtype:
            out.append(f"subtype: {self.game_subtype}")
        if self.camera and self.camera_explicit:
            out.append(f"camera (stated): {self.camera.value}")
        if self.theme:
            out.append(f"setting/theme: {self.theme} (biome={self.biome.value}, lighting="
                       f"{self.lighting.value if self.lighting else 'day'})")
        for e in self.enemies:
            out.append(f"enemy: {e.label}{' x' + str(e.count) if e.count else ''}{' (ranged)' if e.ranged else ''}"
                       f"{' (boss)' if e.boss else ''}")
        for c in self.collectibles:
            out.append(f"collectible: {c.label}{' x' + str(c.count) if c.count else ''}")
        for sw in self.switches:
            out.append(f"interactive switch/terminal: {sw.label}{' x' + str(sw.count) if sw.count else ''}")
        for h in self.hazards:
            out.append(f"hazard: {h}")
        if self.weapons:
            out.append(f"weapons: {', '.join(self.weapons)}")
        if self.mechanics:
            out.append(f"mechanics: {', '.join(self.mechanics)}")
        if self.wants_goal:
            out.append(f"goal: reach the {self.goal_target or 'exit'}")
        if self.has_guards:
            out.append("guards that catch the player (stealth)")
        if self.has_npc:
            out.append("an NPC quest giver")
        if self.waves:
            out.append(f"waves: {self.waves}")
        if self.laps:
            out.append(f"laps: {self.laps}")
        if self.survive_seconds:
            out.append(f"win by surviving {self.survive_seconds} seconds")
        if self.time_limit_seconds:
            out.append(f"time limit: {self.time_limit_seconds} seconds")
        if self.score_target:
            out.append(f"win at score {self.score_target}")
        if self.lives:
            out.append(f"player lives: {self.lives}")
        if self.difficulty:
            out.append(f"difficulty: {self.difficulty}")
        if self.double_jump:
            out.append("mechanic: double jump")
        if self.ranged_player is True:
            out.append("player attacks with a ranged weapon")
        elif self.ranged_player is False:
            out.append("player attacks in melee")
        out.extend(f"rule: {r}" for r in self.custom_rules)
        out.extend(f"note: {n}" for n in self.mechanics_notes)
        return out


def _pascal(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", text or "").strip()
    return "".join(part.capitalize() for part in cleaned.split()) or "GameForgeProject"


def _to_int(tok: str) -> Optional[int]:
    tok = tok.lower().strip()
    if tok.isdigit():
        return int(tok)
    return _NUMBER_WORDS.get(tok)


def _plural_re(noun: str) -> str:
    if noun.endswith("y") and noun not in ("key", "relay"):
        return noun[:-1] + r"(?:y|ies)"
    if noun.endswith(("s", "x", "sh", "ch")):
        return noun + r"(?:es)?"
    if noun.endswith("f"):
        return noun[:-1] + r"(?:f|ves)"
    if noun == "mummy":
        return r"mumm(?:y|ies)"
    return noun + r"s?"


def _singularize(word: str) -> str:
    w = word.strip()
    low = w.lower()
    if low.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if low.endswith(("xes", "ches", "shes", "sses")):
        return w[:-2]
    if low.endswith("ves") and len(w) > 4:
        return w[:-3] + "f"
    if low.endswith("s") and not low.endswith(("ss", "us", "is")) and len(w) > 3:
        return w[:-1]
    return w


def _color_from_label(label: str, default: str = "#00E5FF") -> str:
    low = label.lower()
    if any(k in low for k in ("fire", "lava", "thermal", "magma", "flame", "solar", "ember")):
        return "#FF5722"
    if any(k in low for k in ("ice", "frost", "cryo", "glacier", "snow")):
        return "#5DADE2"
    if any(k in low for k in ("toxic", "acid", "poison", "bio", "venom", "slime")):
        return "#58D68D"
    if any(k in low for k in ("shadow", "void", "dark", "phantom", "wraith", "arcane")):
        return "#8E44AD"
    if any(k in low for k in ("gold", "brass", "solar", "amber", "relic", "treasure")):
        return "#F4D03F"
    digest = hashlib.md5(low.encode("utf-8")).hexdigest()[:6].upper()
    return f"#{digest}" if default == "hash" else default


def _count_before(text: str, noun_re: str) -> Tuple[bool, Optional[int], int]:
    adj = r"(?!(?:and|or|with|of|the|to|in|on|at|for|game|games|that|which|where|while|then|from|by|a|an)\b)[a-z\-]+\s+"
    m = re.search(rf"\b{_NUM}\s+(?:{adj}){{0,2}}?{noun_re}\b", text)
    if m:
        n = _to_int(m.group(1))
        return True, n, m.start()
    m = re.search(rf"\b{noun_re}\b", text)
    if m:
        m2 = re.match(r"\s*(?:[:=x×]|\(x?)\s*(\d{1,4})", text[m.end():])
        return True, (int(m2.group(1)) if m2 else None), m.start()
    return False, None, -1


def _seconds(num: str, unit: str) -> Optional[int]:
    n = _to_int(num)
    if n is None:
        return None
    unit = unit.lower()
    if unit.startswith(("min", "m")) and not unit.startswith("ms"):
        return n * 60
    return n


def _derive_title(prompt: str, brief: "PromptBrief") -> Optional[str]:
    m = re.search(
        r'\b(?:called|named|titled|title[d:]?)\s*["\'“”]?([A-Za-z0-9][\w\s\'\-:!]{1,48}?)["\'“”]?(?:[.,!?;\n]|$|\s+(?:against|with|vs|versus|for|that|and|in|on|at|where|using|which|about)\b)',
        prompt,
        re.I,
    )
    if m:
        t = re.sub(r"\s+", " ", m.group(1)).strip(" -:'\"")
        if t:
            return t[:60]
    m = re.search(r'["“]([^"”]{2,48})["”]', prompt)
    if m:
        return m.group(1).strip()[:60]
    return None


def _synth_title(brief: "PromptBrief") -> str:
    parts: List[str] = []
    theme_word = {
        "volcano": "Volcano", "ice": "Frost", "snow_ice": "Frost", "desert": "Desert", "desert_sand": "Desert",
        "forest": "Forest", "island": "Island", "space": "Orbital", "cyber": "Neon", "scifi_metal": "Reactor",
        "dungeon": "Dungeon", "haunted": "Shadow", "castle": "Citadel", "stone_wood": "Keep",
        "city": "Metro", "candy": "Sugar", "toon_flat": "Toon", "ocean": "Abyssal",
    }.get(brief.theme or "", "")
    if brief.game_subtype in ("snake", "sudoku", "chess", "checkers", "tetris", "minesweeper"):
        return brief.game_subtype.title()
    if brief.game_subtype == "racing":
        return f"{theme_word + ' ' if theme_word else ''}Grand Prix"[:60]
    if brief.game_subtype == "tower_defense":
        return f"{theme_word + ' ' if theme_word else ''}Bastion Defense"[:60]
    if brief.enemies:
        parts.append(brief.enemies[0].label)
    elif brief.collectibles:
        parts.append(brief.collectibles[0].label)
    elif brief.switches:
        parts.append(brief.switches[0].label)
    if theme_word and theme_word not in parts:
        parts.append(theme_word)
    if brief.genre in (Genre.GRID_BOARD, Genre.PUZZLE, Genre.CARD_BATTLER):
        for _g, kws, _w in GENRE_KEYWORDS:
            if _g == brief.genre:
                for kw in kws:
                    if re.search(rf"\b{re.escape(kw)}\b", brief.prompt.lower()) and kw not in ("board game", "card", "cards", "logic", "puzzle"):
                        return kw.title().replace("Tic Tac Toe", "Tic-Tac-Toe")[:60]
    suffix = {
        Genre.PLATFORMER: "Run", Genre.ARENA_COMBAT: "Siege" if brief.waves else "Arena", Genre.TOP_DOWN_SHOOTER: "Vanguard",
        Genre.DUNGEON_CRAWLER: "Protocol" if brief.theme == "cyber" else "Depths", Genre.EXPLORATION: "Expedition",
        Genre.ACTION_ADVENTURE: "Quest", Genre.PUZZLE: "Matrix", Genre.GRID_BOARD: "Tactics", Genre.CARD_BATTLER: "Deck",
    }.get(brief.genre or Genre.CUSTOM, "Odyssey")
    if brief.survive_seconds and brief.genre in (Genre.ARENA_COMBAT, Genre.TOP_DOWN_SHOOTER):
        suffix = "Survival"
    if brief.wants_goal and ESCAPE.search(brief.prompt):
        suffix = "Escape"
    if not parts:
        m = re.search(r"\b((?:[a-z][a-z\-']+\s+){1,2})(?:game|mission|adventure)\b", brief.prompt.lower())
        if m:
            words = [w for w in m.group(1).split() if w not in _STOP_TITLE]
            if words:
                return " ".join(w.capitalize() for w in words)[:60]
    parts.append(suffix)
    title = " ".join(dict.fromkeys(parts))
    return title[:60] if title else "Dynamic Adventure"


def _detect_subtype(text: str, brief: PromptBrief) -> Optional[str]:
    """Detect structural gameplay archetype from prompt semantics."""
    if re.search(r"\b(sudoku|number\s+constraint\s+grid|9x9\s+number)\b", text):
        return "sudoku"
    if re.search(r"\bchess\b", text):
        return "chess"
    if re.search(r"\b(checkers|draughts)\b", text):
        return "checkers"
    if re.search(r"\b(minesweeper|hidden\s+mine\s+grid)\b", text):
        return "minesweeper"
    if re.search(r"\b(roll\s+and\s+move|race\s+board|linear\s+path\s+board|track\s+board)\b", text):
        return "roll_and_move"
    if re.search(r"\b(ludo|parcheesi)\b", text):
        return "ludo"
    if re.search(r"\b(tetris|falling\s+tetromino|falling\s+block\s+puzzle)\b", text):
        return "tetris"
    if re.search(r"\bsnake\b", text) and not re.search(r"\bladders?\b", text) and re.search(r"\b(grid|grow|apple|food|tail|classic|arcade)\b", text):
        return "snake"
    if re.search(r"\b(connect\s+(?:four|4)|four\s+in\s+a\s+row|4\s+in\s+a\s+row)\b", text):
        return "connect_four"
    if re.search(r"\b(gomoku|five\s+in\s+a\s+row|5\s+in\s+a\s+row|omok|renju)\b", text):
        return "gomoku"
    if re.search(r"\b(tic[- ]tac[- ]toe|tictactoe|noughts\s+and\s+crosses)\b", text):
        return "tic_tac_toe"
    if re.search(r"\b(tower\s+defense|defend\s+the\s+(?:base|core|nexus|crystal)|turret\s+defense|lane\s+defense)\b", text):
        return "tower_defense"
    if re.search(r"\b(racing|race\s+track|racer|kart|time\s+trial|driving\s+game|car\s+race|hoverbike|speedway|circuit)\b", text):
        return "racing"
    if re.search(r"\b(bomb\s+defusal|defuse\s+the\s+bomb|plant\s+the\s+bomb|tactical\s+shooter|tactical\s+fps)\b", text):
        return "tactical_fps"
    if re.search(r"\b(roguelike|roguelite|rogue-like)\b", text):
        return "roguelike"
    if brief.has_guards and re.search(r"\b(stealth|sneak|infiltrat|heist|undetected)\b", text):
        return "stealth"
    return None


def _extract_custom_rules(prompt: str, brief: Optional[PromptBrief] = None) -> List[str]:
    """Extract explicit rule/trigger clauses AND synthesize dynamic rules from stated mechanics/resources."""
    rules: List[str] = []
    if not prompt:
        return rules
    sentences = re.split(r"[.;!\n]+", prompt)
    rule_pat = re.compile(
        r"\b(when(?:ever)?\s+[^,.;]{4,90}|every\s+\d+\s*(?:seconds?|secs?|s|waves?|kills?)\s+[^,.;]{3,90}"
        r"|on\s+(?:pickup|kill|death|low\s+health|wave\s+clear|damage|switch|hack|ability)\s+[^,.;]{3,90}"
        r"|if\s+(?:player|health|score|time|oxygen|shield|boss)\s+[^,.;]{4,90}"
        r"|collecting\s+[^,.;]{3,60}\s+(?:restores?|grants?|heals?|gives?|boosts?|unlocks?)\s+[^,.;]{3,60}"
        r"|killing\s+[^,.;]{3,60}\s+(?:restores?|grants?|heals?|gives?|spawns?)\s+[^,.;]{3,60}"
        r"|(?:use|activate|trigger|press)\s+(?:the\s+|a\s+)?[a-z\s]+?(?:ability|smoke bomb|spell)[^,.;]{0,60}"
        r"|in\s+phase\s*2\s+[^,.;]{3,80})",
        re.I,
    )
    for sent in sentences:
        s = sent.strip()
        if not s:
            continue
        m = rule_pat.search(s)
        if m:
            clause = re.sub(r"\s+", " ", s).strip()[:160]
            if clause and clause not in rules:
                rules.append(clause)

    # Synthesize rules for stated dynamic mechanics/resources if not already captured
    low = prompt.lower()
    if brief is not None:
        if "smoke bomb" in low or "invisibility" in low or "(q)" in low or "ability" in low:
            if not any("ability" in r.lower() or "stealth" in r.lower() or "smoke" in r.lower() for r in rules):
                rules.append("When player activates smoke bomb ability (Q), activate stealth for 5 seconds and emit player.ability_used")
        if ("boss" in low or "phase 2" in low or "necromancer" in low or "lord" in low) and not any("boss" in r.lower() for r in rules):
            rules.append("When boss health drops below 50%, transition to boss phase 2, enrage boss, and summon minion wave")
        if (brief.key_pickups or "keys" in low) and (brief.has_doors or "gate" in low or "vault" in low or "door" in low):
            if not any("unlock" in r.lower() or "key" in r.lower() for r in rules):
                rules.append(f"When player collects {brief.key_pickups or 3} ancient keys, unlock the vault gate")
        if "oxygen" in low or "air supply" in low:
            if not any("oxygen" in r.lower() for r in rules):
                rules.append("Every 5 seconds drain 10 oxygen; on pickup restore 25 oxygen and 15 score")
        if "shield" in low and not any("shield" in r.lower() for r in rules):
            rules.append("When player takes damage, absorb impact with shield and grant 10 score on enemy kill")
        if "combo" in low and not any("combo" in r.lower() for r in rules):
            rules.append("On enemy kill grant 35 bonus combo points and restore 10 health when low health")
        if brief.switches and not any("switch" in r.lower() or "terminal" in r.lower() or "hack" in r.lower() for r in rules):
            sw_lbl = brief.switches[0].label
            rules.append(f"When player activates {sw_lbl}, award 50 score and unlock security doors")

    return rules[:8]


def _extract_open_vocab_entities(text: str, brief: PromptBrief) -> None:
    """Extract arbitrary open-vocabulary collectibles, enemies, switches, and hazards from syntactic roles."""
    existing_enemy_nouns = {e.noun.lower() for e in brief.enemies} | {e.label.lower() for e in brief.enemies}
    existing_coll_nouns = {c.noun.lower() for c in brief.collectibles} | {c.label.lower() for c in brief.collectibles}

    # 1. Interactive Switches / Terminals / Consoles / Relays / Braziers / Anvils
    for noun, label in SWITCH_NOUNS.items():
        found, count, _ = _count_before(text, _plural_re(noun))
        if found and not any(sw.label == label for sw in brief.switches):
            brief.switches.append(NamedThing(noun=noun, label=label, count=count or 3, color="#00F5D4"))

    # 2. Open-vocabulary Collectibles following collection verbs
    coll_verb_matches = re.finditer(
        rf"\b(?:collects?|gathers?|recovers?|salvages?|retrieves?|steals?|harvests?|mines?|grabs?|picks?\s+up|finds?|loots?)\s+(?:all\s+(?:the\s+)?)?(?:{_NUM}\s+)?([a-z][a-z\-]+(?:\s+[a-z][a-z\-]+){{0,2}})\b",
        text,
    )
    ignore_nouns = _STOP_TITLE | {
        "all", "them", "it", "enough", "more", "points", "score", "health", "ammo", "weapons",
        "enemies", "guards", "hazards", "while", "before", "until", "without", "through", "across",
    }
    for m in coll_verb_matches:
        cnt = _to_int(m.group(1)) if m.group(1) else None
        raw_phrase = m.group(2).strip()
        words = [w for w in raw_phrase.split() if w not in ignore_nouns and len(w) > 2]
        if not words:
            continue
        head = _singularize(words[-1])
        if head in ignore_nouns or head in SWITCH_NOUNS or head in ENEMY_NOUNS or head in HAZARD_NOUNS:
            continue
        full_label = " ".join([w.capitalize() for w in words[:-1]] + [head.capitalize()])[:40]
        if full_label.lower() not in existing_coll_nouns and not brief.collectibles:
            brief.collectibles.append(
                NamedThing(
                    noun=head,
                    label=full_label,
                    count=cnt or 6,
                    color=_color_from_label(full_label, "#00E5FF"),
                )
            )
            existing_coll_nouns.add(full_label.lower())

    # 3. Open-vocabulary Hostiles following combat/evasion phrases ("waves of frost golems", "dodging plasma drones")
    enemy_verb_matches = re.finditer(
        rf"\b(?:waves?\s+of|hordes?\s+of|swarms?\s+of|fighting|fights?|battles?|battling|against|defeat(?:s|ing)?|slay(?:s|ing)?|dodg(?:es?|ing)|evad(?:es?|ing)|avoid(?:s|ing)?)\s+(?:{_NUM}\s+)?([a-z][a-z\-]+(?:\s+[a-z][a-z\-]+){{0,2}})\b",
        text,
    )
    for m in enemy_verb_matches:
        cnt = _to_int(m.group(1)) if m.group(1) else None
        raw_phrase = m.group(2).strip()
        words = [w for w in raw_phrase.split() if w not in ignore_nouns and len(w) > 2]
        if not words:
            continue
        head = _singularize(words[-1])
        if head in ignore_nouns or head in COLLECTIBLE_NOUNS or head in SWITCH_NOUNS or head in HAZARD_NOUNS:
            continue
        if head in ("obstacle", "hazard", "trap", "pit", "wall", "barrier", "traffic"):
            continue
        full_label = " ".join([w.capitalize() for w in words[:-1]] + [head.capitalize()])[:40]
        if full_label.lower() not in existing_enemy_nouns and head not in existing_enemy_nouns and len(brief.enemies) < 3:
            is_ranged = any(k in raw_phrase for k in ("ranged", "plasma", "laser", "blaster", "artillery", "drone", "turret", "sniper", "mage"))
            is_boss = any(k in raw_phrase for k in ("boss", "giant", "colossus", "titan", "overlord", "ancient", "queen", "king", "lord"))
            brief.enemies.append(
                NamedThing(
                    noun=head,
                    label=full_label,
                    count=cnt,
                    color=_color_from_label(full_label, "#C0392B"),
                    ranged=is_ranged,
                    boss=is_boss,
                )
            )
            if is_boss and not brief.boss_name:
                brief.boss_name = full_label
            existing_enemy_nouns.add(full_label.lower())

    # 4. Boss entity extraction ("defeat the Necromancer Lord", "Dragon Overlord", "Lich King", "ancient Shadow Archon")
    boss_matches = re.finditer(
        rf"\b(?:defeat|slay|destroy|face|kill|against|vanquish|fight|fights|battle|battles|confront|confronts)\s+(?:the\s+)?([a-z][a-z\-]+(?:\s+[a-z][a-z\-]+){{0,2}})\b",
        text,
    )
    for m in boss_matches:
        raw_phrase = m.group(1).strip()
        words = [w for w in raw_phrase.split() if w not in ignore_nouns and len(w) > 2]
        if not words:
            continue
        if any(b_kw in raw_phrase for b_kw in ("lord", "overlord", "boss", "king", "queen", "titan", "archon", "colossus", "dragon", "lich", "necromancer")):
            head = _singularize(words[-1])
            full_label = " ".join([w.capitalize() for w in words[:-1]] + [head.capitalize()])[:40]
            if full_label.lower() not in existing_enemy_nouns and (not any(e.boss for e in brief.enemies) or all(e.label == "Boss" for e in brief.enemies if e.boss)):
                is_ranged = any(k in raw_phrase for k in ("necromancer", "lich", "mage", "wizard", "archon", "dragon"))
                boss_thing = NamedThing(
                    noun=head,
                    label=full_label,
                    count=1,
                    color="#8E1616",
                    ranged=is_ranged,
                    boss=True,
                )
                brief.enemies = [e for e in brief.enemies if e.label != "Boss"]
                brief.enemies.insert(0, boss_thing)
                brief.boss_name = full_label
                existing_enemy_nouns.add(full_label.lower())
                break

    if not brief.boss_name and any(e.boss for e in brief.enemies):
        brief.boss_name = next(e.label for e in brief.enemies if e.boss)

    # 5. Key and Lock Gate Extraction ("find 3 ancient keys to unlock the vault gate")
    key_gate_m = re.search(
        rf"\b(?:find|collect|gather|recover)\s+({_NUM}\s+)?([a-z\s]+?keys?)\s+to\s+(?:unlock|open)\s+(?:the\s+)?([a-z\s]+?(?:gate|door|vault))\b",
        text,
    )
    if key_gate_m:
        k_cnt = _to_int(key_gate_m.group(1)) if key_gate_m.group(1) else 3
        k_raw = key_gate_m.group(2).strip()
        d_raw = key_gate_m.group(3).strip()
        k_label = " ".join(w.capitalize() for w in k_raw.split() if w not in ignore_nouns)
        d_label = " ".join(w.capitalize() for w in d_raw.split() if w not in ignore_nouns)
        k_label = _singularize(k_label) or "Ancient Key"
        d_label = d_label or "Vault Gate"
        brief.key_pickups = k_cnt or 3
        brief.interactive_doors = 1
        brief.has_doors = True
        if not any("key" in c.noun.lower() for c in brief.collectibles):
            brief.collectibles.append(
                NamedThing(noun="key", label=k_label, count=brief.key_pickups, color="#FFD700")
            )
            existing_coll_nouns.add(k_label.lower())


def analyze_prompt(prompt: str) -> PromptBrief:
    text = " " + re.sub(r"\s+", " ", (prompt or "").lower().replace("’", "'")) + " "
    brief = PromptBrief(prompt=prompt or "")

    scores: Dict[Genre, float] = {}
    for genre, kws, weight in GENRE_KEYWORDS:
        for kw in kws:
            if re.search(rf"\b{re.escape(kw)}\b", text):
                scores[genre] = scores.get(genre, 0.0) + weight * (1.0 + 0.15 * kw.count(" "))
    brief.genre_scores = {g.value: round(s, 2) for g, s in scores.items()}

    for cam, pat in CAMERA_PATTERNS:
        if pat.search(text):
            brief.camera = cam
            brief.camera_explicit = True
            break

    best_theme, best_hits = None, 0
    for theme_id, spec in THEMES.items():
        hits = sum(1 for kw in spec["kw"] if re.search(rf"\b{re.escape(kw)}\b", text))
        if hits > best_hits:
            best_theme, best_hits = theme_id, hits
    if best_theme:
        spec = THEMES[best_theme]
        brief.theme = best_theme
        brief.biome = spec["biome"]
        brief.lighting = spec["lighting"]
        brief.palette = list(spec["palette"])
        brief.music_mood = spec["music"]
        brief.ambience = spec["ambience"]
    if re.search(r"\b(night|midnight|dark|darkness|moonlit)\b", text):
        brief.lighting = Lighting.NIGHT
    elif re.search(r"\b(sunset|dusk|evening|twilight)\b", text):
        brief.lighting = Lighting.DUSK
    elif re.search(r"\b(indoors?|inside a|interior)\b", text):
        brief.lighting = Lighting.INDOOR
    if re.search(r"\b(low[- ]poly|lowpoly)\b", text):
        brief.art_style = "low_poly"
    elif re.search(r"\b(toon|cartoon|cel[- ]shaded|cute)\b", text):
        brief.art_style = "toon"
    elif re.search(r"\b(realistic|photoreal)\b", text):
        brief.art_style = "realistic"

    seen_labels = set()
    for noun, (label, ranged, color) in ENEMY_NOUNS.items():
        found, count, _ = _count_before(text, _plural_re(noun))
        if not found or label in seen_labels:
            continue
        if noun in ("enemy", "foe", "shooter") and any(e.label not in ("Enemy", "Foe") for e in brief.enemies):
            continue
        if noun == "shooter" and re.search(r"\b(top[- ]down|twin[- ]stick|first[- ]person|arena|space|3d|2d|tactical)\s+shooter\b|\bshooter (game|where)\b", text):
            continue
        if noun == "turret" and re.search(r"\b(tower\s+defense|defend\s+the\s+(?:base|core|nexus)|build\s+turrets?|place\s+turrets?)\b", text):
            continue
        if noun == "crawler" and re.search(r"\bdungeon\s+crawlers?\b", text) and not re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|waves?\s+of|enemy|enemies|giant|mutant|shadow)\s+crawlers?\b", text):
            continue
        if noun == "boss" and re.search(r"\bboss\s+(arena|fight|battle|encounter|room|chamber|level|zone)\b", text):
            continue
        seen_labels.add(label)
        boss = noun in ("boss", "dragon", "leviathan") or bool(re.search(rf"\b(boss|giant|huge|ancient)\s+{_plural_re(noun)}\b", text))
        brief.enemies.append(NamedThing(noun=noun, label=label, count=count, color=color, ranged=ranged, boss=boss))
        if boss and not brief.boss_name and label != "Boss":
            brief.boss_name = label
    if brief.enemies and re.search(r"\b(enemies|they|that|which)\s+(?:can\s+)?(shoot|fire|throw|cast)\b|\b(shooting|ranged|armed)\s+(enemies|foes)\b", text):
        brief.enemies[0].ranged = True

    for noun, (label, color) in COLLECTIBLE_NOUNS.items():
        if noun in ("core", "part", "cell", "item", "ring", "letter", "package") and not re.search(
                rf"\b(collects?|gathers?|grabs?|finds?|picks?\s+up|recovers?|delivers?|salvages?|steals?|loots?)\b[^.]{{0,40}}\b{_plural_re(noun)}\b", text):
            continue
        if noun == "star" and re.search(r"\bstar(ship|s? wars?)\b", text):
            continue
        if re.search(rf"\b{noun}\s+(land|world|kingdom|island|cave|caves|caverns?|city|planet|forest|mountain|valley|system|temple|palace|tower)\b", text) \
                and not re.search(rf"\b(collects?|gathers?|finds?|grabs?|steals?|loots?|salvages?)\b[^.]{{0,30}}\b{_plural_re(noun)}\b", text):
            continue
        found, count, _ = _count_before(text, _plural_re(noun))
        if not found or any(c.label == label for c in brief.collectibles):
            continue
        if noun in ("pickup", "collectible", "item", "loot") and brief.collectibles:
            continue
        brief.collectibles.append(NamedThing(noun=noun, label=label, count=count, color=color))

    merged: List[NamedThing] = []
    for c in brief.collectibles:
        prev = merged[-1] if merged else None
        if prev and re.search(rf"\b{prev.noun}\s+{_plural_re(c.noun)}\b", text):
            merged[-1] = NamedThing(noun=c.noun, label=f"{prev.label} {c.label}"[:40], count=prev.count or c.count, color=prev.color)
        elif prev and re.search(rf"\b{c.noun}\s+{_plural_re(prev.noun)}\b", text):
            merged[-1] = NamedThing(noun=prev.noun, label=f"{c.label} {prev.label}"[:40], count=c.count or prev.count, color=c.color)
        else:
            merged.append(c)
    brief.collectibles = merged

    # Run open-vocabulary extraction for novel entities, switches, and collectibles
    _extract_open_vocab_entities(text, brief)

    for noun, label in HAZARD_NOUNS.items():
        if re.search(rf"\b{_plural_re(noun)}\b", text) and label not in brief.hazards:
            if noun == "fire" and re.search(r"\b(fire|shoot)s?\s+(at|bullets|projectiles|arrows|lasers)\b", text):
                continue
            if noun == "mine" and brief.theme == "dungeon" and not re.search(r"\b(land ?mines?|mines? explode)\b", text):
                continue
            if noun == "pit" and re.search(r"\b(called|named|titled)\s+[^.,!?;\n]*\bpit\b", text) and not re.search(r"\b(spike|bottomless|acid|fire|deep)\s+pits?\b|\bpits?\s+(of|with|and)\b", text):
                continue
            if noun == "laser" and re.search(r"\blaser\s+(gun|rifle|pistol|blaster)s?\b", text):
                continue
            brief.hazards.append(label)

    m = GOAL_PHRASES.search(text)
    if m:
        brief.wants_goal = True
        brief.goal_target = m.group(2)
    elif ESCAPE.search(text) or re.search(r"\b(finish line|end of the level|get to the end)\b", text):
        brief.wants_goal = True
        brief.goal_target = "exit"
    brief.has_guards = bool(re.search(r"\b(guards?|sentr(?:y|ies)|patrol(?:s|ling)?|stealth|sneak(?:ing)?|without being (?:seen|spotted|caught)|undetected)\b", text))
    brief.has_npc = bool(re.search(r"\b(npc|villager|hermit|quest ?giver|merchant|shopkeeper|wizard who|old man|talk to)\b", text))
    brief.has_doors = bool(re.search(r"\b(door|doors|gate|gates|vault|airlock|locked|unlock|key to)\b", text))
    brief.has_checkpoints = bool(re.search(r"\bcheckpoints?\b", text))
    brief.has_moving_platforms = bool(re.search(r"\bmoving platforms?\b|\bplatforms? (?:that )?move\b|\belevators?\b", text))

    m = re.search(rf"\b{_NUM}\s+(?:\w+\s+)?waves?\b", text) or re.search(r"\bwaves?\s*[:=]?\s*(\d{1,3})\b", text)
    if m:
        brief.waves = _to_int(m.group(1))
    elif re.search(r"\b(waves?|horde|endless|tower\s+defense)\b", text):
        brief.waves = 5 if re.search(r"\b(endless|tower\s+defense)\b", text) else 3

    m_laps = re.search(rf"\b{_NUM}\s+laps?\b", text) or re.search(r"\blaps?\s*[:=]?\s*(\d{1,2})\b", text)
    if m_laps:
        brief.laps = _to_int(m_laps.group(1))
    m_cp = re.search(rf"\b{_NUM}\s+checkpoints?\b", text)
    if m_cp:
        brief.checkpoints = _to_int(m_cp.group(1))
    m_phases = re.search(rf"\b{_NUM}\s+(?:boss\s+)?phases?\b", text)
    if m_phases:
        brief.boss_phases = _to_int(m_phases.group(1))

    m = re.search(rf"\bsurviv(?:e|al|ing)\s+(?:for\s+)?{_NUM}\s*(seconds?|secs?|s|minutes?|mins?)\b", text) or \
        re.search(rf"\blast\s+(?:for\s+)?{_NUM}\s*(seconds?|secs?|minutes?|mins?)\b", text)
    if m:
        brief.survive_seconds = _seconds(m.group(1), m.group(2))
    m = re.search(rf"\b(?:within|in under|under|before|in)\s+{_NUM}\s*(seconds?|secs?|minutes?|mins?)\b", text) or \
        re.search(rf"\b{_NUM}\s*(seconds?|secs?|minutes?|mins?)\s+(?:time limit|timer|to (?:escape|finish|win|collect|reach))\b", text) or \
        re.search(rf"\btime limit (?:of\s+)?{_NUM}\s*(seconds?|secs?|minutes?|mins?)\b", text)
    if m and not brief.survive_seconds:
        brief.time_limit_seconds = _seconds(m.group(1), m.group(2))
    elif re.search(r"\b(time limit|timer runs out|before time runs out|against the clock|countdown|before oxygen runs out)\b", text) and not brief.survive_seconds:
        brief.time_limit_seconds = 120
    m = re.search(r"\b(?:score|points?|reach)\s+(?:of\s+|at least\s+)?(\d{2,6})\s*(?:points?)?\b", text) or \
        re.search(r"\b(\d{2,6})\s+points\b", text)
    if m:
        brief.score_target = int(m.group(1))
    m = re.search(rf"\b{_NUM}\s+lives\b", text) or re.search(r"\blives\s*[:=]?\s*(\d{1,2})\b", text)
    if m:
        brief.lives = _to_int(m.group(1))
    m = re.search(r"\b(\d{2,5})\s*(?:hp|health|hit points)\b", text) or re.search(r"\b(?:hp|health)\s*[:=]?\s*(\d{2,5})\b", text)
    if m:
        brief.player_health = int(m.group(1))

    if re.search(r"\b(very hard|brutal|hardcore|nightmare|insane|extreme|souls?like|difficult|challenging|hard)\b", text):
        brief.difficulty = "hard"
    elif re.search(r"\b(easy|casual|relaxing|relaxed|chill|kids?|beginner|cozy)\b", text):
        brief.difficulty = "easy"
    if re.search(r"\b(huge|massive|vast|enormous|giant (?:world|map|level)|large|big (?:world|map|level))\b", text):
        brief.level_size = "large"
    elif re.search(r"\b(medium|mid-sized)\b", text):
        brief.level_size = "medium"
    elif re.search(r"\b(tiny|small|compact|short)\b", text):
        brief.level_size = "small"

    for w_noun, (w_label, is_ranged) in WEAPON_NOUNS.items():
        if re.search(rf"\b{_plural_re(w_noun)}\b", text):
            if w_noun == "laser" and not re.search(r"\blaser\s+(gun|rifle|pistol|blaster|weapon|cannon)s?\b", text):
                continue
            if w_label not in brief.weapons:
                brief.weapons.append(w_label)
            if is_ranged:
                brief.ranged_player = True
            elif brief.ranged_player is None:
                brief.ranged_player = False

    if re.search(r"\b(gun|guns|shotguns?|rifles?|pistols?|revolvers?|smg|uzi|crossbows?|shoot|shoots|shooting|shooter|"
                 r"blasters?|laser gun|bow|arrows?|fireballs?|magic missiles?|spells?|cannons?|turret|weapons? that fire|harpoon|railgun)\b", text):
        brief.ranged_player = True
    if re.search(r"\b(sword|axe|hammer|punch|punches|kick|melee|fists?|blade|dagger|katana|spear|club|scythe)\b", text):
        brief.ranged_player = False if brief.ranged_player is None else brief.ranged_player

    brief.double_jump = bool(re.search(r"\b(double[- ]jump|triple[- ]jump|air jump)\b", text))
    brief.sprint = bool(re.search(r"\b(sprint|dash|run fast|speed boost|nitro|boost|afterburner)\b", text))
    if re.search(r"\bdash(?:ing)?\b", text):
        brief.mechanics.append("dash")
    if re.search(r"\b(wall[- ]?jump|wall[- ]?run)\b", text):
        brief.mechanics.append("wall_jump")
        brief.mechanics_notes.append("wall-jump traversal with enhanced air control and multi-jump")
        brief.double_jump = True
    if re.search(r"\b(grappl\w*|hookshot|tether|swing)\b", text):
        brief.mechanics.append("grapple")
        brief.mechanics_notes.append("grapple impulse traversal")
        brief.double_jump = True
    if re.search(r"\b(jetpack|fly|flying|thruster|submersible|submarine|zero[- ]gravity|0g)\b", text):
        brief.mechanics.append("jetpack")
        brief.mechanics_notes.append("thruster flight with multi-jump impulse and reduced gravity")
        brief.double_jump = True
    if re.search(r"\b(glide|gliding|glider)\b", text):
        brief.mechanics.append("glide")
        brief.mechanics_notes.append("gliding descent with reduced gravity scale and high air control")
        brief.double_jump = True
    if brief.has_guards or re.search(r"\b(stealth|sneak|infiltrat|undetected)\b", text):
        brief.mechanics.append("stealth")
    if re.search(r"\b(oxygen|air supply|breath)\b", text):
        brief.mechanics.append("oxygen_hazard_drain")
    if re.search(r"\b(shield|energy barrier|armor)\b", text):
        brief.mechanics.append("shield_recharge")
    if re.search(r"\b(combo|multiplier|score streak)\b", text):
        brief.mechanics.append("combo_multiplier")
    if re.search(r"\b(inventory|loot|crafting|craft|forge)\b", text):
        brief.mechanics.append("inventory")
    if brief.has_npc or re.search(r"\b(quest|dialogue|mission)\b", text):
        brief.mechanics.append("quest")

    if re.search(r"\b(smoke bomb|invisibility|smoke screen|cloaking|cloak)\b", text) or (brief.has_guards and re.search(r"\b(ability|skill|\(q\))\b", text)):
        if "stealth" not in brief.mechanics:
            brief.mechanics.append("stealth")
        if "stealth_smoke_bomb" not in brief.mechanics:
            brief.mechanics.append("stealth_smoke_bomb")
        if "smoke_bomb" not in brief.player_abilities:
            brief.player_abilities.append("smoke_bomb")
            brief.ability_key_binds["smoke_bomb"] = "Q"
    elif re.search(r"\b(ability|skill|spell)\s*(?:\(([a-z0-9]+)\))?\b", text):
        m_ab = re.search(r"\b([a-z_]+)\s+ability\s*(?:\(([a-z0-9]+)\))?\b", text)
        ab_name = m_ab.group(1) if m_ab else "special_ability"
        ab_key = (m_ab.group(2) if m_ab and m_ab.group(2) else "Q").upper()
        if ab_name not in brief.player_abilities:
            brief.player_abilities.append(ab_name)
            brief.ability_key_binds[ab_name] = ab_key
        if ab_name not in brief.mechanics:
            brief.mechanics.append(ab_name)
    if any(e.boss for e in brief.enemies) or re.search(r"\b(boss|overlord|lord|phase\s*2)\b", text):
        if "boss_fight" not in brief.mechanics:
            brief.mechanics.append("boss_fight")
        if "multi_phase_boss" not in brief.mechanics:
            brief.mechanics.append("multi_phase_boss")
    if brief.key_pickups or (brief.has_doors and any("key" in c.noun.lower() for c in brief.collectibles)):
        if "key_lock_gate" not in brief.mechanics:
            brief.mechanics.append("key_lock_gate")

    brief.game_subtype = _detect_subtype(text, brief)

    if brief.game_subtype == "racing" or re.search(r"\b(racing|race|racer|kart|cars?|vehicles?|driving|drive|hoverbike|speedway)\b", text):
        brief.game_subtype = "racing"
        for m_tag in ("vehicle_driving", "lap_progression", "checkpoint_splits"):
            if m_tag not in brief.mechanics:
                brief.mechanics.append(m_tag)
        brief.mechanics_notes.append("high-speed vehicle racing circuit with checkpoint splits and lap counter")
        brief.has_checkpoints = True
        brief.laps = brief.laps or 3
        brief.checkpoints = brief.checkpoints or 4
        brief.wants_goal = True
        brief.goal_target = brief.goal_target or "finish line"
        if not brief.time_limit_seconds and not brief.survive_seconds:
            brief.time_limit_seconds = 150
        brief.difficulty = brief.difficulty or "normal"
        brief.sprint = True

    if brief.game_subtype == "tower_defense":
        for m_tag in ("turret_defense", "lane_waves", "base_defense"):
            if m_tag not in brief.mechanics:
                brief.mechanics.append(m_tag)
        brief.mechanics_notes.append("multi-lane tower defense with autonomous turrets, creep waves, and defendable base")
        brief.ranged_player = True
        brief.waves = brief.waves or 5
        if not brief.enemies:
            brief.enemies.append(NamedThing(noun="creep", label="Lane Creep", count=8, color="#C0392B", ranged=False))

    if brief.game_subtype == "tactical_fps":
        brief.camera = brief.camera or CameraKind.FIRST_PERSON
        if not brief.camera_explicit:
            brief.camera = CameraKind.FIRST_PERSON
        brief.ranged_player = True
        if not brief.enemies:
            brief.enemies.append(NamedThing(noun="soldier", label="Hostile Operative", count=6, color="#6B5A3C", ranged=True))

    if re.search(r"\b(multiplayer|online|co-?op|pvp|2 players|two players|split[- ]screen)\b", text) and not brief.is_board_like:
        brief.unsupported.append("online/local multiplayer for action games (built as single player)")
    m = re.search(r"\b(\d)\s*players?\b", text)
    if m:
        brief.players = max(1, min(8, int(m.group(1))))

    brief.custom_rules = _extract_custom_rules(prompt or "", brief=brief)

    brief.genre = _resolve_genre(scores, brief, text)
    if brief.camera is None:
        brief.camera = _default_camera(brief)

    brief.title = _derive_title(prompt or "", brief) or _synth_title(brief)
    return brief


def _resolve_genre(scores: Dict[Genre, float], brief: PromptBrief, text: str) -> Genre:
    if brief.game_subtype in ("sudoku", "tetris", "snake", "minesweeper"):
        return Genre.PUZZLE
    if brief.game_subtype in ("chess", "checkers", "roll_and_move", "ludo", "connect_four", "gomoku", "tic_tac_toe"):
        return Genre.GRID_BOARD
    if brief.game_subtype == "tower_defense":
        return Genre.ARENA_COMBAT
    if brief.game_subtype == "roguelike":
        return Genre.DUNGEON_CRAWLER
    if brief.game_subtype == "racing":
        return Genre.PLATFORMER

    if scores:
        best = max(scores.items(), key=lambda kv: kv[1])[0]
    else:
        best = None
    if best is None or scores.get(best, 0) < 1.5:
        if brief.enemies and (brief.waves or brief.survive_seconds):
            best = Genre.ARENA_COMBAT
        elif brief.enemies and brief.ranged_player and brief.camera == CameraKind.TOP_DOWN:
            best = Genre.TOP_DOWN_SHOOTER
        elif brief.theme == "dungeon" or (brief.enemies and brief.wants_goal and (brief.has_doors or brief.switches)):
            best = Genre.DUNGEON_CRAWLER
        elif brief.has_guards or brief.switches:
            best = Genre.DUNGEON_CRAWLER if re.search(
                r"\b(vault|bank|museum|facility|base|building|mansion|prison|lab|office|castle|bunker|warehouse|station|server|monastery)\b",
                text,
            ) else Genre.EXPLORATION
        elif brief.collectibles and brief.wants_goal and not brief.enemies:
            best = Genre.PLATFORMER
        elif brief.collectibles and re.search(r"\b(collect|gather|find|recover|steal|loot|retrieve|salvage|search for|hunt for)\b", text):
            best = Genre.EXPLORATION
        elif brief.enemies:
            best = Genre.ARENA_COMBAT
        elif brief.collectibles or brief.has_npc:
            best = Genre.EXPLORATION
        elif best is None:
            best = Genre.ACTION_ADVENTURE
    if best == Genre.ARENA_COMBAT and brief.camera == CameraKind.TOP_DOWN and brief.ranged_player and brief.game_subtype != "tower_defense":
        best = Genre.TOP_DOWN_SHOOTER
    if best == Genre.ARENA_COMBAT and not brief.enemies and brief.collectibles and brief.wants_goal:
        best = Genre.PLATFORMER
    if brief.camera == CameraKind.SIDE_SCROLLER and best not in (Genre.GRID_BOARD, Genre.CARD_BATTLER, Genre.PUZZLE):
        best = Genre.PLATFORMER
    return best


def _default_camera(brief: PromptBrief) -> CameraKind:
    g = brief.genre
    if g in (Genre.GRID_BOARD, Genre.CARD_BATTLER, Genre.PUZZLE):
        return CameraKind.FIXED_BOARD
    if g == Genre.TOP_DOWN_SHOOTER or brief.game_subtype == "tower_defense":
        return CameraKind.TOP_DOWN
    if g == Genre.ARENA_COMBAT:
        return CameraKind.TOP_DOWN if not brief.ranged_player else CameraKind.THIRD_PERSON
    return CameraKind.THIRD_PERSON


def _difficulty_scale(diff: str) -> float:
    return {"easy": 0.7, "hard": 1.4}.get(diff, 1.0)


def _enemy_entity(e: NamedThing, diff: str, default_count: int) -> DraftEntity:
    scale = _difficulty_scale(diff)
    count = max(1, min(50, e.count or default_count))
    kind = EntityKind.RANGED_ENEMY if e.ranged else EntityKind.ENEMY
    props: Dict[str, Any] = {
        "attack_damage": round((10.0 if e.ranged else 15.0) * scale, 1),
        "max_health": round((35.0 if e.ranged else 50.0) * scale * (5.0 if e.boss else 1.0), 1),
        "move_speed": round((280.0 if e.ranged else 330.0) * (0.9 + 0.1 * scale), 1),
    }
    if e.boss:
        count = 1
        props["bIsBoss"] = True
        props["BossName"] = e.label
        props["BossPhase"] = 1
        props["max_health"] = round(150.0 * scale, 1)
        props["attack_damage"] = round(props["attack_damage"] * 1.8, 1)
    return DraftEntity(
        kind=kind,
        count=count,
        note=e.label[:60],
        props=props,
        tags=[f"label:{e.label}"[:40], f"color:{e.color}"] + (["boss"] if e.boss else []),
    )


def _board_props_for_brief(brief: PromptBrief) -> Tuple[str, Dict[str, Any]]:
    """Return parameterized (note, props) for a grid/board/puzzle game."""
    st = brief.game_subtype or ""
    p_low = brief.prompt.lower()
    m_grid = re.search(r"\b(\d{1,2})\s*[x×]\s*(\d{1,2})\b", p_low)
    explicit_size = int(m_grid.group(1)) if m_grid else None

    if st == "sudoku" or "sudoku" in p_low or "number constraint" in p_low:
        return "Constraint Grid", {
            "board_mode": "sudoku",
            "board_size": explicit_size or 9,
            "win_length": explicit_size or 9,
            "vs_ai": False,
            "cell_size_cm": 80.0,
        }
    if st == "chess" or "chess" in p_low:
        return "Tactical Board", {
            "board_mode": "chess",
            "board_size": explicit_size or 8,
            "win_length": explicit_size or 8,
            "vs_ai": brief.players < 2,
            "ai_level": "minimax",
            "cell_size_cm": 100.0,
            "players": max(2, brief.players),
        }
    if st == "checkers" or any(k in p_low for k in ("checkers", "draughts")):
        return "Capture Grid Board", {
            "board_mode": "checkers",
            "board_size": explicit_size or 8,
            "win_length": explicit_size or 8,
            "vs_ai": brief.players < 2,
            "ai_level": "greedy",
            "cell_size_cm": 100.0,
            "players": max(2, brief.players),
        }
    if st == "minesweeper" or "minesweeper" in p_low:
        return "Deduction Grid", {
            "board_mode": "minesweeper",
            "board_size": explicit_size or 9,
            "win_length": explicit_size or 9,
            "vs_ai": False,
            "cell_size_cm": 80.0,
        }
    if st == "roll_and_move" or "roll and move" in p_low or "race board" in p_low:
        return "Roll and Move Board", {
            "board_mode": "roll_and_move",
            "board_size": explicit_size or 10,
            "win_length": explicit_size or 10,
            "dice_sides": 6,
            "players": max(2, brief.players),
            "vs_ai": brief.players < 2,
            "cell_size_cm": 100.0,
        }
    if st == "ludo" or any(k in p_low for k in ("ludo", "parcheesi")):
        return "Four-Track Race Board", {
            "board_mode": "ludo",
            "board_size": explicit_size or 15,
            "win_length": 6,
            "dice_sides": 6,
            "players": max(2, min(4, brief.players if brief.players > 1 else 4)),
            "vs_ai": True,
            "cell_size_cm": 90.0,
        }
    if st == "tetris" or "tetris" in p_low or "falling block" in p_low:
        return "Falling Block Matrix", {
            "board_mode": "tetris",
            "board_size": explicit_size or 10,
            "win_length": explicit_size or 10,
            "gravity": True,
            "vs_ai": False,
            "cell_size_cm": 70.0,
        }
    if st == "snake":
        return "Grid Trail Arena", {
            "board_mode": "snake",
            "board_size": explicit_size or 15,
            "win_length": explicit_size or 15,
            "vs_ai": False,
            "cell_size_cm": 70.0,
        }
    if st == "connect_four" or any(k in p_low for k in ("connect four", "connect 4", "four in a row")):
        return "Gravity Alignment Board", {
            "board_mode": "connect_four",
            "board_size": explicit_size or 7,
            "win_length": 4,
            "gravity": True,
            "vs_ai": brief.players < 2,
            "ai_level": "greedy",
            "cell_size_cm": 120.0,
        }
    if st == "gomoku" or any(k in p_low for k in ("gomoku", "five in a row", "5 in a row")):
        return "Strategy Grid Board", {
            "board_mode": "gomoku",
            "board_size": explicit_size or 15,
            "win_length": 5,
            "vs_ai": brief.players < 2,
            "ai_level": "greedy",
            "cell_size_cm": 90.0,
        }
    return "Game Board", {
        "board_mode": "n_in_a_row",
        "board_size": explicit_size or 3,
        "win_length": min(explicit_size or 3, 5),
        "vs_ai": brief.players < 2,
        "ai_level": "perfect",
        "cell_size_cm": 120.0,
    }


def brief_to_draft(brief: PromptBrief) -> DesignDraft:
    """Build a complete, playable DesignDraft from the prompt's extracted facts and mechanics."""
    genre = brief.genre or Genre.ACTION_ADVENTURE
    diff = brief.difficulty or "normal"
    entities: List[DraftEntity] = []
    win: List[DraftWin] = []
    lose: List[DraftLose] = []

    for i, e in enumerate(brief.enemies[:4]):
        default = 6 if genre in (Genre.ARENA_COMBAT, Genre.TOP_DOWN_SHOOTER) else 4
        entities.append(_enemy_entity(e, diff, default if i == 0 else 3))
    if not brief.enemies and not brief.has_guards and genre in (Genre.ARENA_COMBAT, Genre.TOP_DOWN_SHOOTER, Genre.DUNGEON_CRAWLER):
        entities.append(_enemy_entity(NamedThing("enemy", "Enemy"), diff, 5))

    if brief.game_subtype == "tower_defense":
        entities.append(
            DraftEntity(
                kind=EntityKind.PROP,
                count=4,
                note="Defense Turret",
                props={"recipe": "turret_base", "scale_x": 1.2, "scale_y": 1.2, "scale_z": 1.8},
                tags=["label:Defense Turret", "color:#3FA7D6", "turret", "friendly_tower"],
            )
        )
        entities.append(
            DraftEntity(
                kind=EntityKind.GOAL,
                count=1,
                note="Home Base Core",
                tags=["label:Home Base Core", "color:#00E5FF", "base_core"],
            )
        )

    if brief.game_subtype == "tactical_fps":
        entities.append(
            DraftEntity(
                kind=EntityKind.BOMB_SITE,
                count=2,
                note="Bomb Site A",
                props={"site_id": "A", "plant_seconds": 3.0, "defuse_seconds": 5.0, "fuse_seconds": 35.0},
                tags=["label:Bomb Site A", "bombsite"],
            )
        )

    for c in brief.collectibles[:3]:
        default = {Genre.PLATFORMER: 8, Genre.EXPLORATION: 10, Genre.DUNGEON_CRAWLER: 5}.get(genre, 6)
        entities.append(
            DraftEntity(
                kind=EntityKind.PICKUP,
                count=max(1, min(50, c.count or default)),
                note=c.label[:60],
                props={"value": 1},
                tags=[f"label:{c.label}"[:40], f"color:{c.color}"],
            )
        )
    if not brief.collectibles and not brief.switches and genre in (Genre.PLATFORMER, Genre.EXPLORATION):
        note_lbl = "Speed Boost Pad" if brief.game_subtype == "racing" else "Energy Core"
        col_hex = "#00F5D4" if brief.game_subtype == "racing" else "#F2C230"
        entities.append(
            DraftEntity(
                kind=EntityKind.PICKUP,
                count=6 if brief.game_subtype == "racing" else (8 if genre == Genre.PLATFORMER else 10),
                note=note_lbl,
                tags=[f"label:{note_lbl}", f"color:{col_hex}"],
            )
        )

    for sw in brief.switches[:2]:
        entities.append(
            DraftEntity(
                kind=EntityKind.SWITCH,
                count=max(1, min(12, sw.count or 3)),
                note=sw.label[:60],
                props={"toggle": True},
                tags=[f"label:{sw.label}"[:40], f"color:{sw.color}"],
            )
        )
    if brief.has_doors or brief.switches:
        d_label = "Vault Gate" if (brief.theme in ("dungeon", "gothic_crypt") or brief.key_pickups) else "Security Gate"
        door_props: Dict[str, Any] = {"required_value": 1.0, "open_seconds": 1.0}
        if brief.key_pickups > 0:
            door_props["required_value"] = float(brief.key_pickups)
            door_props["required_stat"] = "game.counter.keys_collected"
        entities.append(
            DraftEntity(
                kind=EntityKind.DOOR,
                count=1,
                note=d_label,
                props=door_props,
                tags=[f"label:{d_label}", "color:#E67E22"],
            )
        )

    for h in brief.hazards[:3]:
        entities.append(
            DraftEntity(
                kind=EntityKind.HAZARD,
                count=3 if genre != Genre.PLATFORMER else 4,
                note=h[:60],
                props={"damage_per_second": 25.0 * _difficulty_scale(diff)},
                tags=[f"label:{h}"[:40]],
            )
        )
    if brief.has_guards:
        entities.append(DraftEntity(kind=EntityKind.GUARD, count=3 if diff != "hard" else 5, note="Guard", tags=["label:Guard", "color:#2C3E50"]))
    if brief.has_npc:
        entities.append(DraftEntity(kind=EntityKind.NPC, count=1, note="Quest Giver", tags=["label:Quest Giver"]))
    if brief.has_checkpoints or genre == Genre.PLATFORMER:
        cp_cnt = brief.checkpoints or (4 if brief.game_subtype == "racing" else 2)
        entities.append(DraftEntity(kind=EntityKind.CHECKPOINT, count=cp_cnt, note="Checkpoint"))
    if brief.has_moving_platforms:
        entities.append(DraftEntity(kind=EntityKind.MOVING_PLATFORM, count=3, note="Moving Platform"))
    if genre in (Genre.GRID_BOARD, Genre.PUZZLE) or brief.game_subtype in (
        "sudoku", "chess", "checkers", "minesweeper", "roll_and_move", "ludo", "tetris", "snake"
    ):
        b_note, b_props = _board_props_for_brief(brief)
        entities.append(DraftEntity(kind=EntityKind.BOARD, count=1, note=b_note, props=b_props))
    if genre in (Genre.EXPLORATION, Genre.ACTION_ADVENTURE):
        entities.append(DraftEntity(kind=EntityKind.LANDMARK, count=1, note="Landmark"))
    if (brief.wants_goal or genre in (Genre.PLATFORMER, Genre.DUNGEON_CRAWLER)) and not any(e.kind == EntityKind.GOAL for e in entities):
        entities.append(
            DraftEntity(
                kind=EntityKind.GOAL,
                count=1,
                note=(brief.goal_target or "exit").title()[:60],
                tags=[f"label:{(brief.goal_target or 'exit').title()}"[:40]],
            )
        )
    if genre in (Genre.ARENA_COMBAT, Genre.TOP_DOWN_SHOOTER) and (brief.waves or not brief.survive_seconds):
        waves = max(1, min(50, brief.waves or (3 if diff != "hard" else 5)))
        per_wave = max(
            2,
            min(
                20,
                (brief.enemies[0].count if brief.enemies and brief.enemies[0].count else 0) // max(1, waves)
                or {"easy": 3, "normal": 4, "hard": 6}[diff],
            ),
        )
        entities.append(
            DraftEntity(
                kind=EntityKind.SPAWNER,
                count=1,
                note="Wave Spawner",
                props={
                    "wave_count": waves,
                    "enemies_per_wave": per_wave,
                    "seconds_between_waves": 4.0 if diff == "hard" else 6.0,
                },
            )
        )

    if brief.survive_seconds:
        win.append(DraftWin(type="survive_seconds", seconds=max(10, min(3600, brief.survive_seconds))))
    if brief.score_target:
        win.append(DraftWin(type="score_at_least", target=max(1, min(10000, brief.score_target))))
    has_pickups = any(e.kind == EntityKind.PICKUP for e in entities)
    has_enemies = any(e.kind in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY) for e in entities)
    has_spawner = any(e.kind == EntityKind.SPAWNER for e in entities)
    stated_collect = bool(brief.collectibles) and bool(
        re.search(r"\b(collect|gather|find|recover|grab|pick up|steal|loot|rescue|save|retrieve|salvage|harvest)\b", brief.prompt, re.I)
    )
    if not win:
        if brief.game_subtype == "racing":
            win.append(DraftWin(type="reach_goal"))
        elif genre in (Genre.ARENA_COMBAT, Genre.TOP_DOWN_SHOOTER) and (has_spawner or has_enemies):
            spawner = next((e for e in entities if e.kind == EntityKind.SPAWNER), None)
            win.append(DraftWin(type="defeat_all", target=int(spawner.props.get("wave_count", 3)) if spawner else None))
        elif genre == Genre.PLATFORMER:
            if stated_collect or has_pickups:
                win.append(DraftWin(type="collect_all"))
            win.append(DraftWin(type="reach_goal"))
        elif genre == Genre.DUNGEON_CRAWLER:
            if stated_collect:
                win.append(DraftWin(type="collect_all"))
            if brief.game_subtype == "roguelike" and has_enemies:
                win.append(DraftWin(type="defeat_all"))
            win.append(DraftWin(type="reach_goal"))
        elif genre in (Genre.EXPLORATION, Genre.ACTION_ADVENTURE, Genre.CUSTOM):
            if has_pickups:
                win.append(DraftWin(type="collect_all"))
            if brief.wants_goal:
                win.append(DraftWin(type="reach_goal"))
            if not win and has_enemies:
                win.append(DraftWin(type="defeat_all"))
            if not win:
                win.append(DraftWin(type="reach_goal"))
        elif genre == Genre.CARD_BATTLER:
            win.append(DraftWin(type="match_win"))
        else:
            win.append(DraftWin(type="board_win"))
    elif stated_collect and not any(w.type == "collect_all" for w in win) and len(win) < 3:
        win.append(DraftWin(type="collect_all"))
    if brief.wants_goal and not any(w.type == "reach_goal" for w in win) and len(win) < 3 and not brief.is_board_like:
        win.append(DraftWin(type="reach_goal"))

    if brief.is_board_like:
        lose = [DraftLose(type="match_loss")] if genre == Genre.CARD_BATTLER else [DraftLose(type="board_loss")]
    else:
        if has_enemies or has_spawner or brief.hazards or brief.lives:
            lose.append(DraftLose(type="health_zero"))
        if brief.has_guards:
            lose.append(DraftLose(type="caught_by_guard"))
        if brief.time_limit_seconds:
            lose.append(DraftLose(type="timer_runs_out", seconds=max(10, min(3600, brief.time_limit_seconds))))
    lose = lose[:3]

    player_props: Dict[str, Any] = {}
    if brief.player_health:
        player_props["max_health"] = float(max(1, min(10000, brief.player_health)))
    if brief.lives:
        player_props["lives"] = max(0, min(99, brief.lives))
    if brief.ranged_player is True:
        player_props["attack_mode"] = "projectile"
    elif brief.ranged_player is False:
        player_props["attack_mode"] = "melee"
    if brief.weapons:
        player_props["weapons"] = list(brief.weapons)
    if genre == Genre.PLATFORMER or brief.double_jump:
        player_props.setdefault("air_control", 0.45)
    if brief.double_jump:
        player_props["double_jump"] = True
        player_props["max_jumps"] = 2
    if "jetpack" in brief.mechanics or "glide" in brief.mechanics:
        player_props["max_jumps"] = 3
        player_props["gravity_scale"] = 0.55
        player_props["air_control"] = 0.85
    elif "wall_jump" in brief.mechanics or "grapple" in brief.mechanics:
        player_props["max_jumps"] = 2
        player_props["air_control"] = 0.80
    if "dash" in brief.mechanics:
        player_props["dash_impulse"] = 1200.0
    if brief.sprint:
        player_props["sprint_multiplier"] = 1.8
    if brief.game_subtype == "racing":
        player_props["move_speed"] = 1100.0
        player_props["sprint_multiplier"] = 2.0
        player_props["jump_velocity"] = 350.0
        player_props["air_control"] = 0.70

    if player_props and not brief.is_board_like:
        p_note = "Race Vehicle" if brief.game_subtype == "racing" else "Player"
        p_tags = ["label:Race Vehicle", "vehicle"] if brief.game_subtype == "racing" else []
        entities.insert(0, DraftEntity(kind=EntityKind.PLAYER, count=1, note=p_note, props=player_props, tags=p_tags))

    size = brief.level_size or (
        "large"
        if brief.game_subtype == "racing"
        else ("medium" if genre in (Genre.EXPLORATION, Genre.ACTION_ADVENTURE) else "small")
    )
    pitch = re.sub(r"\s+", " ", brief.prompt).strip()[:280] or f"A {genre.value.replace('_', ' ')} game"
    arch_payload: Dict[str, Any] = {
        "method": "hybrid_custom",
        "plan_kind": brief.game_subtype or genre.value,
        "custom_capabilities": list(brief.mechanics),
        "target_classes": [f"U{_pascal(brief.title or 'Dynamic')}GameplayRule"],
        "player_abilities": list(brief.player_abilities),
        "mechanics": {
            "active_mechanics": list(brief.mechanics),
            "boss_name": brief.boss_name,
            "boss_phases": brief.boss_phases or (2 if brief.boss_name else 1),
            "key_count": brief.key_pickups,
            "door_count": brief.interactive_doors,
            "weapons": list(brief.weapons),
        },
    }
    valid_music = {"none", "calm", "tense", "heroic", "playful", "boss", "action", "mysterious"}
    return DesignDraft(
        title=(brief.title or _synth_title(brief))[:60],
        genre=genre,
        camera=brief.camera or _default_camera(brief),
        pitch=pitch,
        biome=brief.biome,
        lighting=brief.lighting or Lighting.DAY,
        level_size=size,  # type: ignore[arg-type]
        entities=entities[:20],
        win=win[:3],
        lose=lose,
        difficulty=diff,  # type: ignore[arg-type]
        art_style=(brief.art_style or "stylized"),  # type: ignore[arg-type]
        music_mood=brief.music_mood if brief.music_mood in valid_music else "none",  # type: ignore[arg-type]
        custom_rules=list(brief.custom_rules[:8]),
        questions=[],
        architecture=arch_payload,
    )


def reconcile_draft(draft: DesignDraft, brief: PromptBrief) -> Tuple[DesignDraft, List[str]]:
    """Repair a model draft so it honours every fact the prompt states."""
    fixes: List[str] = []
    data = draft.model_dump()

    if brief.title and _derive_title(brief.prompt, brief) and data["title"] != brief.title:
        data["title"] = brief.title[:60]
        fixes.append(f"title restored to {brief.title!r}")
    if brief.camera_explicit and brief.camera and data["camera"] != brief.camera:
        data["camera"] = brief.camera
        fixes.append(f"camera set to stated {brief.camera.value}")
    if brief.biome != Biome.NONE and data.get("biome") in (Biome.NONE, "none"):
        data["biome"] = brief.biome
        fixes.append(f"biome set to {brief.biome.value}")
    if brief.lighting and data.get("lighting") in (Lighting.DAY, "day") and brief.lighting != Lighting.DAY:
        data["lighting"] = brief.lighting
        fixes.append(f"lighting set to {brief.lighting.value}")
    if brief.difficulty and data.get("difficulty") != brief.difficulty:
        data["difficulty"] = brief.difficulty
        fixes.append(f"difficulty set to {brief.difficulty}")
    if brief.level_size and data.get("level_size") != brief.level_size:
        data["level_size"] = brief.level_size
    if data.get("music_mood") in ("none", None) and brief.music_mood != "none":
        data["music_mood"] = brief.music_mood
    if data.get("art_style") == "stylized" and brief.art_style:
        data["art_style"] = brief.art_style
    if len(brief.prompt) > len(data.get("pitch") or ""):
        data["pitch"] = re.sub(r"\s+", " ", brief.prompt).strip()[:280]

    ents: List[Dict[str, Any]] = list(data.get("entities") or [])
    kinds = [str(getattr(e["kind"], "value", e["kind"])) for e in ents]

    def _has(kind: EntityKind) -> bool:
        return kind.value in kinds

    enemy_idx = [i for i, k in enumerate(kinds) if k in ("enemy", "ranged_enemy")]
    for j, e in enumerate(brief.enemies[:3]):
        want = _enemy_entity(e, brief.difficulty or str(data.get("difficulty", "normal")), 5).model_dump()
        if j < len(enemy_idx):
            cur = ents[enemy_idx[j]]
            if e.count and cur.get("count") != e.count:
                cur["count"] = max(1, min(50, e.count))
                fixes.append(f"{e.label} count set to {e.count}")
            cur_tags = list(cur.get("tags") or [])
            for t in want["tags"]:
                if not any(str(x).split(":")[0] == t.split(":")[0] for x in cur_tags):
                    cur_tags.append(t)
            cur["tags"] = cur_tags[:6]
            if not cur.get("note"):
                cur["note"] = e.label
            if e.ranged and cur["kind"] in (EntityKind.ENEMY, "enemy"):
                cur["kind"] = EntityKind.RANGED_ENEMY
        elif len(ents) < 20:
            ents.append(want)
            kinds.append(str(getattr(want["kind"], "value", want["kind"])))
            fixes.append(f"added missing enemy {e.label}")

    pick_idx = [i for i, k in enumerate(kinds) if k == "pickup"]
    for j, c in enumerate(brief.collectibles[:2]):
        if j < len(pick_idx):
            cur = ents[pick_idx[j]]
            if c.count and cur.get("count") != c.count:
                cur["count"] = max(1, min(50, c.count))
                fixes.append(f"{c.label} count set to {c.count}")
            tags = list(cur.get("tags") or [])
            if not any(str(t).startswith("label:") for t in tags):
                tags.append(f"label:{c.label}"[:40])
            if not any(str(t).startswith("color:") for t in tags):
                tags.append(f"color:{c.color}")
            cur["tags"] = tags[:6]
            cur["note"] = cur.get("note") or c.label
        elif len(ents) < 20:
            ents.append(
                DraftEntity(
                    kind=EntityKind.PICKUP,
                    count=max(1, min(50, c.count or 6)),
                    note=c.label[:60],
                    tags=[f"label:{c.label}"[:40], f"color:{c.color}"],
                ).model_dump()
            )
            kinds.append("pickup")
            fixes.append(f"added missing collectible {c.label}")

    for sw in brief.switches[:2]:
        if not _has(EntityKind.SWITCH) and len(ents) < 20:
            ents.append(
                DraftEntity(
                    kind=EntityKind.SWITCH,
                    count=max(1, min(12, sw.count or 3)),
                    note=sw.label[:60],
                    props={"toggle": True},
                    tags=[f"label:{sw.label}"[:40], f"color:{sw.color}"],
                ).model_dump()
            )
            kinds.append("switch")
            fixes.append(f"added interactive switch {sw.label}")

    if (brief.has_doors or brief.switches) and not _has(EntityKind.DOOR) and len(ents) < 20:
        ents.append(
            DraftEntity(
                kind=EntityKind.DOOR,
                count=1,
                note="Security Gate",
                props={"required_value": 1.0, "open_seconds": 1.0},
                tags=["label:Security Gate"],
            ).model_dump()
        )
        kinds.append("door")
        fixes.append("added door")

    for h in brief.hazards[:2]:
        if not any(k == "hazard" and h.lower() in str(ents[i].get("note", "")).lower() for i, k in enumerate(kinds)) \
                and not (_has(EntityKind.HAZARD) and len(brief.hazards) == 1) and len(ents) < 20:
            ents.append(DraftEntity(kind=EntityKind.HAZARD, count=3, note=h[:60], tags=[f"label:{h}"[:40]]).model_dump())
            kinds.append("hazard")
            fixes.append(f"added missing hazard {h}")
    if brief.has_guards and not _has(EntityKind.GUARD) and len(ents) < 20:
        ents.append(DraftEntity(kind=EntityKind.GUARD, count=3, note="Guard", tags=["label:Guard"]).model_dump())
        kinds.append("guard")
        fixes.append("added guards")
    if brief.has_npc and not _has(EntityKind.NPC) and len(ents) < 20:
        ents.append(DraftEntity(kind=EntityKind.NPC, count=1, note="Quest Giver").model_dump())
        kinds.append("npc")
    if brief.wants_goal and not _has(EntityKind.GOAL) and len(ents) < 20 and not brief.is_board_like:
        ents.append(DraftEntity(kind=EntityKind.GOAL, count=1, note=(brief.goal_target or "exit").title()[:60]).model_dump())
        kinds.append("goal")
        fixes.append("added goal")
    if brief.waves:
        sp = next((e for e, k in zip(ents, kinds) if k == "spawner"), None)
        if sp is not None:
            props = dict(sp.get("props") or {})
            if props.get("wave_count") != brief.waves:
                props["wave_count"] = brief.waves
                sp["props"] = props
                fixes.append(f"wave count set to {brief.waves}")
        elif len(ents) < 20 and not brief.is_board_like:
            ents.append(DraftEntity(kind=EntityKind.SPAWNER, count=1, note="Wave Spawner", props={"wave_count": brief.waves}).model_dump())
            kinds.append("spawner")
            fixes.append(f"added wave spawner ({brief.waves} waves)")

    if brief.is_board_like or brief.game_subtype in (
        "sudoku", "chess", "checkers", "minesweeper", "roll_and_move", "ludo", "tetris", "snake"
    ):
        b_ent = next((e for e, k in zip(ents, kinds) if k == "board"), None)
        b_note, b_props = _board_props_for_brief(brief)
        if b_ent is not None:
            props = dict(b_ent.get("props") or {})
            for pk, pv in b_props.items():
                props.setdefault(pk, pv)
            b_ent["props"] = props
            if not b_ent.get("note"):
                b_ent["note"] = b_note
        elif len(ents) < 20:
            ents.append(DraftEntity(kind=EntityKind.BOARD, count=1, note=b_note, props=b_props).model_dump())
            kinds.append("board")

    player_props: Dict[str, Any] = {}
    if brief.player_health:
        player_props["max_health"] = float(brief.player_health)
    if brief.lives:
        player_props["lives"] = brief.lives
    if brief.ranged_player is True:
        player_props["attack_mode"] = "projectile"
    elif brief.ranged_player is False:
        player_props["attack_mode"] = "melee"
    if brief.weapons:
        player_props["weapons"] = list(brief.weapons)
    if brief.double_jump:
        player_props["double_jump"] = True
        player_props["max_jumps"] = 2
    if "jetpack" in brief.mechanics or "glide" in brief.mechanics:
        player_props["max_jumps"] = 3
        player_props["gravity_scale"] = 0.55
        player_props["air_control"] = 0.85
    if "dash" in brief.mechanics:
        player_props["dash_impulse"] = 1200.0
    if brief.sprint:
        player_props["sprint_multiplier"] = 1.8
    if brief.game_subtype == "racing":
        player_props["move_speed"] = 1100.0
        player_props["sprint_multiplier"] = 2.0
    if player_props and not brief.is_board_like:
        pl = next((e for e, k in zip(ents, kinds) if k == "player"), None)
        if pl is None and len(ents) < 20:
            ents.insert(0, DraftEntity(kind=EntityKind.PLAYER, count=1, note="Player", props=player_props).model_dump())
        elif pl is not None:
            props = dict(pl.get("props") or {})
            props.update(player_props)
            pl["props"] = props
    data["entities"] = ents[:20]

    if brief.custom_rules:
        existing_cr = list(data.get("custom_rules") or [])
        for cr in brief.custom_rules:
            if cr not in existing_cr and len(existing_cr) < 8:
                existing_cr.append(cr)
        data["custom_rules"] = existing_cr

    wins = list(data.get("win") or [])
    types = {str(w["type"]) for w in wins}
    if brief.survive_seconds and "survive_seconds" not in types and len(wins) < 3:
        wins.append({"type": "survive_seconds", "seconds": brief.survive_seconds, "target": None})
        fixes.append(f"win: survive {brief.survive_seconds}s")
    if brief.score_target and "score_at_least" not in types and len(wins) < 3:
        wins.append({"type": "score_at_least", "target": brief.score_target, "seconds": None})
    for w in wins:
        if w["type"] == "survive_seconds" and brief.survive_seconds:
            w["seconds"] = brief.survive_seconds
        if w["type"] == "score_at_least" and brief.score_target:
            w["target"] = brief.score_target
        if w["type"] == "collect_all":
            w["target"] = None
    data["win"] = wins[:3] or [{"type": "reach_goal", "target": None, "seconds": None}]
    loses = list(data.get("lose") or [])
    ltypes = {str(lz["type"]) for lz in loses}
    if brief.time_limit_seconds and "timer_runs_out" not in ltypes and len(loses) < 3:
        loses.append({"type": "timer_runs_out", "seconds": brief.time_limit_seconds, "target": None})
        fixes.append(f"lose: time limit {brief.time_limit_seconds}s")
    if brief.has_guards and "caught_by_guard" not in ltypes and len(loses) < 3:
        loses.append({"type": "caught_by_guard", "seconds": None, "target": None})
    data["lose"] = loses[:3]
    data["questions"] = []

    try:
        return DesignDraft.model_validate(data), fixes
    except Exception as exc:
        return draft, [f"reconciliation skipped: {exc}"]


def brief_for_model(brief: PromptBrief) -> str:
    lines = brief.summary_lines()
    if not lines:
        return ""
    return (
        "Facts stated in the user's prompt (your JSON MUST keep every one of these; use the given names in "
        "entity notes and the given counts):\n- " + "\n- ".join(lines)
    )
