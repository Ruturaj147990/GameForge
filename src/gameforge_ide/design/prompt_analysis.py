"""Deterministic prompt analysis: extracts every concrete fact a game prompt states.

Why this exists
---------------
Generated games routinely ignored what the user asked for. The model draft is small and lossy (the schema allows a
280-character pitch, 12 entities and no names), weak local models drop details ("zombies" became generic enemies,
"10 coins" became 5 pickups, "lava volcano" became a grey arena), and without a model the pipeline either fell back to a
hard-coded preset or asked "which preset is this closest to?".

``analyze_prompt`` turns the prompt into a :class:`PromptBrief` - genre, camera, theme, named enemies / collectibles /
hazards with counts, win/lose conditions with their numbers, mechanics and difficulty - without any model. The brief is
used three ways:

* ``brief_for_model``: a compact fact sheet appended to the drafting system prompt so the model is told what it must
  keep;
* ``reconcile_draft``: repairs a model draft that dropped or contradicted stated facts;
* ``brief_to_draft``: a complete offline draft, so a prompt that names no preset still becomes a playable game when no
  model is available.

Everything here is pure, side-effect free and safe to call on any string.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .draft import DesignDraft, DraftEntity, DraftLose, DraftWin
from .gds import Biome, CameraKind, EntityKind, Genre, Lighting

# ── vocabulary ────────────────────────────────────────────────────────────────────────────────────────────────────

# "a"/"an" are deliberately absent: "a game with zombies" must not read as "1 zombie".
_NUMBER_WORDS = {
    "one": 1, "single": 1, "two": 2, "couple": 2, "pair": 2, "three": 3, "few": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "dozen": 12,
    "fifteen": 15, "twenty": 20, "thirty": 30, "fifty": 50, "several": 4, "many": 8, "lots": 10, "hundred": 100,
}
_NUM = r"(\d{1,4}|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")"

# noun -> (canonical singular label, ranged?, hex colour)
ENEMY_NOUNS: Dict[str, Tuple[str, bool, str]] = {
    "zombie": ("Zombie", False, "#5E8C3A"), "skeleton": ("Skeleton", False, "#D8D2C0"),
    "goblin": ("Goblin", False, "#4F8A2E"), "orc": ("Orc", False, "#3F6B2A"), "troll": ("Troll", False, "#6B7F5A"),
    "robot": ("Robot", False, "#8A949E"), "drone": ("Drone", True, "#5A6E80"), "alien": ("Alien", True, "#6FD13B"),
    "invader": ("Invader", True, "#9B5DE5"), "monster": ("Monster", False, "#8E2C48"), "demon": ("Demon", False, "#A3201B"),
    "ghost": ("Ghost", False, "#C9E4F2"), "vampire": ("Vampire", False, "#5C0F1E"), "werewolf": ("Werewolf", False, "#5A4632"),
    "spider": ("Spider", False, "#2B2B2B"), "slime": ("Slime", False, "#5BD16B"), "bat": ("Bat", False, "#3A2E3F"),
    "wolf": ("Wolf", False, "#6E6E6E"), "bandit": ("Bandit", False, "#7A4E2D"), "pirate": ("Pirate", False, "#7B3F2A"),
    "soldier": ("Soldier", True, "#556B2F"), "terrorist": ("Terrorist", True, "#6B5A3C"), "mercenary": ("Mercenary", True, "#4A4A3A"),
    "knight": ("Knight", False, "#A9A9B8"), "ninja": ("Ninja", False, "#1E1E26"), "samurai": ("Samurai", False, "#8C1C13"),
    "archer": ("Archer", True, "#7D8C3A"), "wizard": ("Wizard", True, "#4B3B8F"), "witch": ("Witch", True, "#3B2A5A"),
    "mage": ("Mage", True, "#4C3FA3"), "sorcerer": ("Sorcerer", True, "#5A2E8C"), "turret": ("Turret", True, "#707A84"),
    "cultist": ("Cultist", False, "#4A1F3D"), "mutant": ("Mutant", False, "#7FA13A"), "beast": ("Beast", False, "#6B3E26"),
    "insect": ("Insect", False, "#3E5C1F"), "bug": ("Bug", False, "#466B1F"), "rat": ("Rat", False, "#5E544C"),
    "enemy": ("Enemy", False, "#C0392B"), "foe": ("Foe", False, "#C0392B"), "minion": ("Minion", False, "#B5563A"),
    "boss": ("Boss", False, "#7D0A0A"), "dragon": ("Dragon", True, "#A01818"), "shooter": ("Gunner", True, "#5D6D7E"),
    "gunner": ("Gunner", True, "#5D6D7E"), "sniper": ("Sniper", True, "#3D4B3A"), "tank": ("Tank", True, "#59614A"),
    "mummy": ("Mummy", False, "#C2B280"), "golem": ("Golem", False, "#7D7468"), "yeti": ("Yeti", False, "#E8F0F5"),
    "shark": ("Shark", False, "#5C7A8C"), "crab": ("Crab", False, "#C0482B"), "elemental": ("Elemental", True, "#E86A17"),
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
}
HAZARD_NOUNS: Dict[str, str] = {
    "lava": "Lava", "spike": "Spikes", "trap": "Trap", "acid": "Acid", "fire": "Fire", "flame": "Flames",
    "poison": "Poison", "laser": "Laser", "pit": "Pit", "saw": "Saw", "mine": "Mine", "electric": "Electric Floor",
    "quicksand": "Quicksand", "thorn": "Thorns", "toxic": "Toxic Waste", "radiation": "Radiation",
}
GOAL_PHRASES = re.compile(
    r"\b(reach|get to|find|escape (?:through|via|to)|make it to|arrive at|enter|exit through|go to|head to)\s+"
    r"(?:the\s+)?(exit|portal|door|gate|flag|finish(?: line)?|goal|summit|top|castle|temple|ship|rocket|helicopter|"
    r"tower|cave|end|beacon|lighthouse|altar|throne|spaceship|escape pod|extraction(?: point)?|boat)\b", re.I)
ESCAPE = re.compile(r"\b(escape|get out|break out|flee)\b", re.I)

# Themes: keyword -> (theme id, biome, lighting, palette, music, ambience)
THEMES: Dict[str, Dict[str, Any]] = {
    "volcano": {"kw": ("volcano", "volcanic", "lava", "magma", "inferno", "hell", "molten"), "biome": Biome.MOUNTAIN,
                "lighting": Lighting.DUSK, "palette": ["#2B1B17", "#E25822", "#FFB347", "#5C1A0B"],
                "music": "tense", "ambience": "wind"},
    "ice": {"kw": ("ice", "icy", "snow", "snowy", "frozen", "arctic", "glacier", "winter", "tundra", "polar"),
            "biome": Biome.MOUNTAIN, "lighting": Lighting.DAY, "palette": ["#DCEBF5", "#7FB3D5", "#2E86C1", "#F4F6F7"],
            "music": "calm", "ambience": "wind"},
    "desert": {"kw": ("desert", "sand", "sandy", "dune", "dunes", "pyramid", "egypt", "egyptian", "oasis", "canyon",
                      "wild west", "western", "cowboy"),
               "biome": Biome.DESERT, "lighting": Lighting.DAY, "palette": ["#E8C07D", "#C2703D", "#7A4A2A", "#F6E3B4"],
               "music": "heroic", "ambience": "wind"},
    "forest": {"kw": ("forest", "woods", "woodland", "jungle", "grove", "swamp", "enchanted", "fairy", "elf", "elven",
                      "druid", "garden", "meadow"),
               "biome": Biome.FOREST, "lighting": Lighting.DAY, "palette": ["#2D5A27", "#6A994E", "#A7C957", "#6B4226"],
               "music": "calm", "ambience": "forest"},
    "island": {"kw": ("island", "beach", "tropical", "pirate", "ocean", "sea", "coast", "lagoon"),
               "biome": Biome.ISLAND, "lighting": Lighting.DAY, "palette": ["#F4E1B0", "#2EC4B6", "#0B7A75", "#3A7D44"],
               "music": "playful", "ambience": "wind"},
    "space": {"kw": ("space", "spaceship", "space station", "galaxy", "planet", "mars", "moon", "asteroid", "alien",
                     "cosmic", "starship", "orbit"),
              "biome": Biome.NONE, "lighting": Lighting.NIGHT, "palette": ["#0B0C2A", "#3A0CA3", "#4CC9F0", "#F72585"],
              "music": "tense", "ambience": "none"},
    "cyber": {"kw": ("cyber", "cyberpunk", "neon", "synthwave", "hacker", "futuristic", "sci-fi", "scifi", "robot",
                     "tech", "laboratory", "lab", "facility"),
              "biome": Biome.INDOOR, "lighting": Lighting.NIGHT, "palette": ["#14002E", "#00F5D4", "#F15BB5", "#3A0CA3"],
              "music": "tense", "ambience": "city"},
    "dungeon": {"kw": ("dungeon", "crypt", "catacomb", "tomb", "cave", "cavern", "mine", "underground", "sewer",
                       "labyrinth", "maze"),
                "biome": Biome.DUNGEON, "lighting": Lighting.INDOOR, "palette": ["#2E2A27", "#6D5D4B", "#C8A165", "#4A3B2C"],
                "music": "tense", "ambience": "dungeon"},
    "haunted": {"kw": ("haunted", "spooky", "horror", "creepy", "graveyard", "cemetery", "halloween", "ghost", "zombie",
                       "undead", "vampire", "gothic"),
                "biome": Biome.FOREST, "lighting": Lighting.NIGHT, "palette": ["#1B1B2F", "#5B5F97", "#B8B8D1", "#7D3C98"],
                "music": "tense", "ambience": "forest"},
    "castle": {"kw": ("castle", "medieval", "kingdom", "knight", "fortress", "keep", "citadel", "royal"),
               "biome": Biome.MOUNTAIN, "lighting": Lighting.DAY, "palette": ["#8D8D8D", "#4F5D75", "#BFC0C0", "#A4161A"],
               "music": "heroic", "ambience": "wind"},
    "city": {"kw": ("city", "urban", "street", "rooftop", "downtown", "metro", "subway", "town", "village"),
             "biome": Biome.NONE, "lighting": Lighting.DUSK, "palette": ["#3D405B", "#81B29A", "#F2CC8F", "#E07A5F"],
             "music": "heroic", "ambience": "city"},
    "candy": {"kw": ("candy", "sweet", "dessert", "cake", "cartoon", "cute", "toy", "toys", "kids"),
              "biome": Biome.NONE, "lighting": Lighting.DAY, "palette": ["#FFC8DD", "#BDE0FE", "#FFAFCC", "#A2D2FF"],
              "music": "playful", "ambience": "none"},
    "ocean": {"kw": ("underwater", "aquatic", "reef", "deep sea", "atlantis", "submarine"),
              "biome": Biome.ISLAND, "lighting": Lighting.DUSK, "palette": ["#03045E", "#0077B6", "#00B4D8", "#90E0EF"],
              "music": "calm", "ambience": "none"},
}

GENRE_KEYWORDS: List[Tuple[Genre, Tuple[str, ...], float]] = [
    (Genre.ARENA_COMBAT, ("counter strike", "counter-strike", "bomb defusal", "defuse the bomb", "plant the bomb",
                          "tactical shooter", "cs go", "csgo", "valorant"), 4.0),
    (Genre.PLATFORMER, ("racing", "race", "racer", "kart", "time trial", "speedrun", "runner", "endless runner"), 2.2),
    (Genre.GRID_BOARD, ("chess", "checkers", "draughts", "tic tac toe", "tic-tac-toe", "connect four", "board game",
                        "gomoku", "othello", "reversi", "snakes and ladders", "ludo", "monopoly"), 3.0),
    (Genre.CARD_BATTLER, ("card", "cards", "deck", "deckbuilder", "deck builder", "hand of cards", "tcg", "ccg"), 3.0),
    (Genre.PUZZLE, ("puzzle", "sudoku", "match three", "match-3", "tetris", "sokoban", "logic"), 2.5),
    (Genre.PLATFORMER, ("platformer", "platform", "platforms", "jump", "jumping", "parkour", "obby", "obstacle course",
                        "side-scroller", "side scroller", "sidescroller", "mario", "climb", "double jump"), 2.0),
    (Genre.TOP_DOWN_SHOOTER, ("top-down shooter", "top down shooter", "twin stick", "twin-stick", "bullet hell",
                              "shmup", "shoot em up", "shoot 'em up"), 3.0),
    (Genre.ARENA_COMBAT, ("arena", "wave", "waves", "horde", "survive", "survival", "gladiator", "brawler", "beat em up",
                          "hack and slash", "hack-and-slash", "fight", "fighting", "combat", "battle", "defend",
                          "tower defense", "shooter", "shoot", "shooting", "fps", "gun", "guns"), 1.2),
    (Genre.DUNGEON_CRAWLER, ("dungeon", "crawler", "roguelike", "rogue-like", "roguelite", "crypt", "catacomb",
                             "labyrinth", "maze", "rooms"), 2.0),
    (Genre.EXPLORATION, ("explore", "exploration", "open world", "open-world", "wander", "discover", "adventure",
                         "landscape", "hike", "hiking", "sandbox"), 1.5),
    (Genre.ACTION_ADVENTURE, ("quest", "rpg", "hero", "villager", "npc", "kingdom", "story"), 1.0),
]

CAMERA_PATTERNS: List[Tuple[CameraKind, re.Pattern]] = [
    (CameraKind.FIRST_PERSON, re.compile(r"\b(first[- ]person|fps|1st[- ]person|counter[- ]strike|doom|cod)\b", re.I)),
    (CameraKind.TOP_DOWN, re.compile(r"\b(top[- ]down|topdown|bird'?s[- ]eye|isometric|twin[- ]stick|overhead)\b", re.I)),
    (CameraKind.SIDE_SCROLLER, re.compile(r"\b(side[- ]?scroll(?:er|ing)?|2d platformer|2\.5d|metroidvania|mario)\b", re.I)),
    (CameraKind.THIRD_PERSON, re.compile(r"\b(third[- ]person|3rd[- ]person|over the shoulder)\b", re.I)),
]

_STOP_TITLE = {"a", "an", "the", "game", "make", "create", "build", "me", "please", "i", "want", "where", "with", "and",
               "of", "in", "on", "to", "for", "that", "which", "you", "player", "players", "simple", "fun", "cool",
               "awesome", "small", "big", "3d", "2d", "new", "my", "some", "who", "must", "can", "has", "have"}


# ── data ──────────────────────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class NamedThing:
    noun: str           # matched noun as written ("zombies")
    label: str          # display label ("Zombie")
    count: Optional[int] = None
    color: str = "#C0392B"
    ranged: bool = False
    boss: bool = False


@dataclass
class PromptBrief:
    prompt: str
    title: Optional[str] = None
    genre: Optional[Genre] = None
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
    hazards: List[str] = field(default_factory=list)
    goal_target: Optional[str] = None
    wants_goal: bool = False
    has_guards: bool = False
    has_npc: bool = False
    has_doors: bool = False
    has_checkpoints: bool = False
    has_moving_platforms: bool = False
    waves: Optional[int] = None
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
    unsupported: List[str] = field(default_factory=list)
    mechanics_notes: List[str] = field(default_factory=list)

    @property
    def is_board_like(self) -> bool:
        return self.genre in (Genre.GRID_BOARD, Genre.CARD_BATTLER, Genre.PUZZLE)

    def summary_lines(self) -> List[str]:
        """Human/LLM readable list of the facts the prompt states."""
        out: List[str] = []
        if self.title:
            out.append(f"title: {self.title}")
        if self.genre:
            out.append(f"genre: {self.genre.value}")
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
        for h in self.hazards:
            out.append(f"hazard: {h}")
        if self.wants_goal:
            out.append(f"goal: reach the {self.goal_target or 'exit'}")
        if self.has_guards:
            out.append("guards that catch the player (stealth)")
        if self.has_npc:
            out.append("an NPC quest giver")
        if self.waves:
            out.append(f"waves: {self.waves}")
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
        out.extend(f"note: {n}" for n in self.mechanics_notes)
        return out


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────────────────────

def _to_int(tok: str) -> Optional[int]:
    tok = tok.lower().strip()
    if tok.isdigit():
        return int(tok)
    return _NUMBER_WORDS.get(tok)


def _plural_re(noun: str) -> str:
    if noun.endswith("y") and noun not in ("key",):
        return noun[:-1] + r"(?:y|ies)"
    if noun.endswith(("s", "x", "sh", "ch")):
        return noun + r"(?:es)?"
    if noun.endswith("f"):
        return noun[:-1] + r"(?:f|ves)"
    if noun == "mummy":
        return r"mumm(?:y|ies)"
    return noun + r"s?"


def _count_before(text: str, noun_re: str) -> Tuple[bool, Optional[int], int]:
    """(found, count, position) for '<count> <adjectives> <noun>'."""
    # up to two adjectives between the number and the noun ("12 golden ancient relics"), never function words
    adj = r"(?!(?:and|or|with|of|the|to|in|on|at|for|game|games|that|which|where|while|then|from|by|a|an)\b)[a-z\-]+\s+"
    m = re.search(rf"\b{_NUM}\s+(?:{adj}){{0,2}}?{noun_re}\b", text)
    if m:
        n = _to_int(m.group(1))
        # "a zombie" is not a count statement worth 1 when the noun is plural elsewhere
        return True, n, m.start()
    m = re.search(rf"\b{noun_re}\b", text)
    if m:
        # "zombies: 12" / "zombies (x12)"
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
    m = re.search(r'\b(?:called|named|titled|title[d:]?)\s*["\'“”]?([A-Za-z0-9][\w\s\'\-:!]{1,48}?)["\'“”]?(?:[.,!?;\n]|$|\s+(?:against|with|vs|versus|for|that|and|in|on|at|where|using|which|about)\b)',
                  prompt, re.I)
    if m:
        t = re.sub(r"\s+", " ", m.group(1)).strip(" -:'\"")
        if t:
            return t[:60]
    m = re.search(r'["“]([^"”]{2,48})["”]', prompt)
    if m:
        return m.group(1).strip()[:60]
    return None


def _synth_title(brief: "PromptBrief") -> str:
    """A specific title from the prompt's own nouns ("Zombie Volcano Survival") instead of "Custom Game"."""
    parts: List[str] = []
    theme_word = {
        "volcano": "Volcano", "ice": "Frost", "desert": "Desert", "forest": "Forest", "island": "Island",
        "space": "Star", "cyber": "Neon", "dungeon": "Dungeon", "haunted": "Haunted", "castle": "Castle",
        "city": "City", "candy": "Candy", "ocean": "Abyss",
    }.get(brief.theme or "", "")
    if brief.enemies:
        parts.append(brief.enemies[0].label)
    elif brief.collectibles:
        parts.append(brief.collectibles[0].label)
    if theme_word and theme_word not in parts:
        parts.append(theme_word)
    if brief.genre in (Genre.GRID_BOARD, Genre.PUZZLE, Genre.CARD_BATTLER):
        for _g, kws, _w in GENRE_KEYWORDS:
            if _g == brief.genre:
                for kw in kws:
                    if re.search(rf"\b{re.escape(kw)}\b", brief.prompt.lower()) and kw not in ("board game", "card", "cards", "logic", "puzzle"):
                        return kw.title().replace("Tic Tac Toe", "Tic-Tac-Toe")[:60]
    suffix = {
        Genre.PLATFORMER: "Run", Genre.ARENA_COMBAT: "Siege" if brief.waves else "Arena", Genre.TOP_DOWN_SHOOTER: "Blaster",
        Genre.DUNGEON_CRAWLER: "Depths", Genre.EXPLORATION: "Expedition", Genre.ACTION_ADVENTURE: "Quest",
        Genre.PUZZLE: "Puzzle", Genre.GRID_BOARD: "Board", Genre.CARD_BATTLER: "Cards",
    }.get(brief.genre or Genre.CUSTOM, "Adventure")
    if brief.survive_seconds and brief.genre in (Genre.ARENA_COMBAT, Genre.TOP_DOWN_SHOOTER):
        suffix = "Survival"
    if brief.wants_goal and ESCAPE.search(brief.prompt):
        suffix = "Escape"
    if not parts:
        # Use the prompt's own description ("a racing game" -> "Racing") rather than a generic word.
        m = re.search(r"\b((?:[a-z][a-z\-']+\s+){1,2})game\b", brief.prompt.lower())
        if m:
            words = [w for w in m.group(1).split() if w not in _STOP_TITLE]
            if words:
                return " ".join(w.capitalize() for w in words)[:60]
    parts.append(suffix)
    title = " ".join(dict.fromkeys(parts))
    return title[:60] if title else "Untitled Adventure"


# ── main entry ────────────────────────────────────────────────────────────────────────────────────────────────────

def analyze_prompt(prompt: str) -> PromptBrief:
    text = " " + re.sub(r"\s+", " ", (prompt or "").lower().replace("’", "'")) + " "
    brief = PromptBrief(prompt=prompt or "")

    # Genre scoring (longest phrases weigh more; explicit genre words dominate).
    scores: Dict[Genre, float] = {}
    for genre, kws, weight in GENRE_KEYWORDS:
        for kw in kws:
            if re.search(rf"\b{re.escape(kw)}\b", text):
                scores[genre] = scores.get(genre, 0.0) + weight * (1.0 + 0.15 * kw.count(" "))
    brief.genre_scores = {g.value: round(s, 2) for g, s in scores.items()}

    # Camera
    for cam, pat in CAMERA_PATTERNS:
        if pat.search(text):
            brief.camera = cam
            brief.camera_explicit = True
            break

    # Theme
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

    # Enemies
    seen_labels = set()
    for noun, (label, ranged, color) in ENEMY_NOUNS.items():
        found, count, _ = _count_before(text, _plural_re(noun))
        if not found or label in seen_labels:
            continue
        if noun in ("enemy", "foe", "shooter") and any(e.label not in ("Enemy", "Foe") for e in brief.enemies):
            continue
        # "shooter" as a genre word ("a top-down shooter") is not an enemy
        if noun == "shooter" and re.search(r"\b(top[- ]down|twin[- ]stick|first[- ]person|arena|space|3d|2d)\s+shooter\b|\bshooter (game|where)\b", text):
            continue
        seen_labels.add(label)
        boss = noun in ("boss", "dragon") or bool(re.search(rf"\b(boss|giant|huge)\s+{_plural_re(noun)}\b", text))
        brief.enemies.append(NamedThing(noun=noun, label=label, count=count, color=color, ranged=ranged, boss=boss))
    # "enemies that shoot" / "shooting enemies"
    if brief.enemies and re.search(r"\b(enemies|they|that|which)\s+(?:can\s+)?(shoot|fire|throw|cast)\b|\b(shooting|ranged|armed)\s+(enemies|foes)\b", text):
        brief.enemies[0].ranged = True

    # Collectibles (skip nouns already consumed as enemies / genre words)
    for noun, (label, color) in COLLECTIBLE_NOUNS.items():
        if noun in ("core", "part", "cell", "item", "ring", "letter", "package") and not re.search(
                rf"\b(collect|gather|grab|find|pick up|recover|deliver)\b[^.]{{0,40}}\b{_plural_re(noun)}\b", text):
            continue
        if noun == "star" and re.search(r"\bstar(ship|s? wars?)\b", text):
            continue
        # setting words are not collectibles: "candy land", "crystal caves", "treasure island", "star system"
        if re.search(rf"\b{noun}\s+(land|world|kingdom|island|cave|caves|caverns?|city|planet|forest|mountain|valley|system|temple|palace)\b", text) \
                and not re.search(rf"\b(collect|gather|find|grab|steal|loot)\b[^.]{{0,30}}\b{_plural_re(noun)}\b", text):
            continue
        found, count, _ = _count_before(text, _plural_re(noun))
        if not found or any(c.label == label for c in brief.collectibles):
            continue
        if noun in ("pickup", "collectible", "item", "loot") and brief.collectibles:
            continue
        brief.collectibles.append(NamedThing(noun=noun, label=label, count=count, color=color))
    # "treasure chests", "crystal shards": two collectible nouns in a row are one collectible.
    merged: List[NamedThing] = []
    for c in brief.collectibles:
        prev = merged[-1] if merged else None
        if prev and re.search(rf"\b{prev.noun}\s+{_plural_re(c.noun)}\b", text):
            merged[-1] = NamedThing(noun=c.noun, label=f"{prev.label} {c.label}"[:40], count=prev.count or c.count, color=prev.color)
        elif prev and re.search(rf"\b{c.noun}\s+{_plural_re(prev.noun)}\b", text):
            merged[-1] = NamedThing(noun=prev.noun, label=f"{c.label} {prev.label}"[:40], count=prev.count or c.count, color=c.color)
        else:
            merged.append(c)
    brief.collectibles = merged
    if not brief.collectibles and re.search(r"\b(collect|gather|pick up|grab|steal|rescue|retrieve)\b", text):
        m = re.search(rf"\b(?:collect|gather|pick up|grab|steal|rescue|retrieve)\s+(?:all\s+(?:the\s+)?)?{_NUM}?\s*([a-z]+)", text)
        if m:
            n = _to_int(m.group(1)) if m.group(1) else None
            noun = m.group(2).rstrip("s")
            if noun not in _STOP_TITLE and len(noun) > 2:
                brief.collectibles.append(NamedThing(noun=noun, label=noun.capitalize(), count=n, color="#F2C230"))

    # Hazards
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

    # Goal / guards / npc / doors
    m = GOAL_PHRASES.search(text)
    if m:
        brief.wants_goal = True
        brief.goal_target = m.group(2)
    elif ESCAPE.search(text) or re.search(r"\b(finish line|end of the level|get to the end)\b", text):
        brief.wants_goal = True
        brief.goal_target = "exit"
    brief.has_guards = bool(re.search(r"\b(guards?|sentr(?:y|ies)|patrol(?:s|ling)?|stealth|sneak(?:ing)?|without being (?:seen|spotted|caught)|undetected)\b", text))
    brief.has_npc = bool(re.search(r"\b(npc|villager|hermit|quest ?giver|merchant|shopkeeper|wizard who|old man|talk to)\b", text))
    brief.has_doors = bool(re.search(r"\b(door|doors|gate|gates|locked|unlock|key to)\b", text))
    brief.has_checkpoints = bool(re.search(r"\bcheckpoints?\b", text))
    brief.has_moving_platforms = bool(re.search(r"\bmoving platforms?\b|\bplatforms? (?:that )?move\b|\belevators?\b", text))

    # Numbers: waves, timers, score, lives, health
    m = re.search(rf"\b{_NUM}\s+(?:\w+\s+)?waves?\b", text) or re.search(r"\bwaves?\s*[:=]?\s*(\d{1,3})\b", text)
    if m:
        brief.waves = _to_int(m.group(1))
    elif re.search(r"\b(waves?|horde|endless)\b", text):
        brief.waves = 5 if re.search(r"\bendless\b", text) else 3
    m = re.search(rf"\bsurviv(?:e|al|ing)\s+(?:for\s+)?{_NUM}\s*(seconds?|secs?|s|minutes?|mins?)\b", text) or \
        re.search(rf"\blast\s+(?:for\s+)?{_NUM}\s*(seconds?|secs?|minutes?|mins?)\b", text)
    if m:
        brief.survive_seconds = _seconds(m.group(1), m.group(2))
    m = re.search(rf"\b(?:within|in under|under|before|in)\s+{_NUM}\s*(seconds?|secs?|minutes?|mins?)\b", text) or \
        re.search(rf"\b{_NUM}\s*(seconds?|secs?|minutes?|mins?)\s+(?:time limit|timer|to (?:escape|finish|win|collect|reach))\b", text) or \
        re.search(rf"\btime limit (?:of\s+)?{_NUM}\s*(seconds?|secs?|minutes?|mins?)\b", text)
    if m and not brief.survive_seconds:
        brief.time_limit_seconds = _seconds(m.group(1), m.group(2))
    elif re.search(r"\b(time limit|timer runs out|before time runs out|against the clock|countdown)\b", text) and not brief.survive_seconds:
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

    # Difficulty & size
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

    # Player weapon & mechanics
    if re.search(r"\b(gun|guns|shotguns?|rifles?|pistols?|revolvers?|smg|uzi|crossbows?|shoot|shoots|shooting|shooter|"
                 r"blasters?|laser gun|bow|arrows?|fireballs?|magic missiles?|spells?|cannons?|turret|weapons? that fire)\b", text):
        brief.ranged_player = True
    if re.search(r"\b(sword|axe|hammer|punch|punches|kick|melee|fists?|blade|dagger|katana|spear|club)\b", text):
        brief.ranged_player = False if brief.ranged_player is None else brief.ranged_player
    brief.double_jump = bool(re.search(r"\b(double[- ]jump|triple[- ]jump|air jump)\b", text))
    brief.sprint = bool(re.search(r"\b(sprint|dash|run fast|speed boost)\b", text))
    if re.search(r"\b(wall[- ]?jump|wall[- ]?run|grappl\w*|hookshot|swing)\b", text):
        brief.mechanics_notes.append("wall-jump / grapple traversal is approximated with higher jumps and air control")
        brief.double_jump = True
    if re.search(r"\b(jetpack|fly|flying|glide|gliding)\b", text):
        brief.mechanics_notes.append("flight is approximated with a triple jump and low gravity")
        brief.double_jump = True
    if re.search(r"\b(racing|race|racer|kart|cars?|vehicles?|driving|drive)\b", text):
        brief.unsupported.append("vehicles (built as an on-foot time-trial course with checkpoints)")
        brief.has_checkpoints = True
        brief.wants_goal = True
        brief.goal_target = brief.goal_target or "finish line"
        if not brief.time_limit_seconds and not brief.survive_seconds:
            brief.time_limit_seconds = 150
        brief.difficulty = brief.difficulty or "easy"
        brief.sprint = True
    if re.search(r"\b(counter[- ]strike|bomb defusal|defuse|plant the bomb|tactical shooter|csgo|cs go)\b", text):
        brief.camera = brief.camera or CameraKind.FIRST_PERSON
        if not brief.camera_explicit:
            brief.camera = CameraKind.FIRST_PERSON
        brief.ranged_player = True
        if not brief.enemies:
            brief.enemies.append(NamedThing(noun="terrorist", label="Terrorist", count=6, color="#6B5A3C", ranged=True))
    if re.search(r"\b(multiplayer|online|co-?op|pvp|2 players|two players|split[- ]screen)\b", text) and not brief.is_board_like:
        brief.unsupported.append("online/local multiplayer for action games (built as single player)")
    m = re.search(r"\b(\d)\s*players?\b", text)
    if m:
        brief.players = max(1, min(8, int(m.group(1))))

    # Resolve genre from scores and facts
    brief.genre = _resolve_genre(scores, brief, text)
    if brief.camera is None:
        brief.camera = _default_camera(brief)

    brief.title = _derive_title(prompt or "", brief) or _synth_title(brief)
    return brief


def _resolve_genre(scores: Dict[Genre, float], brief: PromptBrief, text: str) -> Genre:
    if scores:
        best = max(scores.items(), key=lambda kv: kv[1])[0]
    else:
        best = None
    # facts nudge the decision when keywords are weak
    if best is None or scores.get(best, 0) < 1.5:
        if brief.enemies and (brief.waves or brief.survive_seconds):
            best = Genre.ARENA_COMBAT
        elif brief.enemies and brief.ranged_player and brief.camera == CameraKind.TOP_DOWN:
            best = Genre.TOP_DOWN_SHOOTER
        elif brief.theme == "dungeon" or (brief.enemies and brief.wants_goal and brief.has_doors):
            best = Genre.DUNGEON_CRAWLER
        elif brief.has_guards:
            # Stealth: indoor heists play best in rooms, outdoor infiltration in an open level.
            best = Genre.DUNGEON_CRAWLER if re.search(
                r"\b(vault|bank|museum|facility|base|building|mansion|prison|lab|office|castle|bunker|warehouse)\b",
                text) else Genre.EXPLORATION
        elif brief.collectibles and brief.wants_goal and not brief.enemies:
            best = Genre.PLATFORMER
        elif brief.collectibles and re.search(r"\b(collect|gather|find|recover|steal|loot|retrieve|search for|hunt for)\b", text):
            best = Genre.EXPLORATION
        elif brief.enemies:
            best = Genre.ARENA_COMBAT
        elif brief.collectibles or brief.has_npc:
            best = Genre.EXPLORATION
        elif best is None:
            best = Genre.ACTION_ADVENTURE
    if best == Genre.ARENA_COMBAT and brief.camera == CameraKind.TOP_DOWN and brief.ranged_player:
        best = Genre.TOP_DOWN_SHOOTER
    if best == Genre.ARENA_COMBAT and not brief.enemies and brief.collectibles and brief.wants_goal:
        best = Genre.PLATFORMER
    # A side view is a course along one axis: build it as a platformer unless the prompt is explicitly a board game.
    if brief.camera == CameraKind.SIDE_SCROLLER and best not in (Genre.GRID_BOARD, Genre.CARD_BATTLER, Genre.PUZZLE):
        best = Genre.PLATFORMER
    return best


def _default_camera(brief: PromptBrief) -> CameraKind:
    g = brief.genre
    if g in (Genre.GRID_BOARD, Genre.CARD_BATTLER, Genre.PUZZLE):
        return CameraKind.FIXED_BOARD
    if g == Genre.TOP_DOWN_SHOOTER:
        return CameraKind.TOP_DOWN
    if g == Genre.ARENA_COMBAT:
        return CameraKind.TOP_DOWN if not brief.ranged_player else CameraKind.THIRD_PERSON
    return CameraKind.THIRD_PERSON


# ── brief -> draft / reconciliation ───────────────────────────────────────────────────────────────────────────────

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
        count = min(count, 3) if e.count else 1
        props["attack_damage"] = round(props["attack_damage"] * 1.8, 1)
    return DraftEntity(kind=kind, count=count, note=e.label[:60], props=props,
                       tags=[f"label:{e.label}"[:40], f"color:{e.color}"] + (["boss"] if e.boss else []))


def brief_to_draft(brief: PromptBrief) -> DesignDraft:
    """A complete, playable DesignDraft built only from the prompt's stated facts plus genre conventions."""
    genre = brief.genre or Genre.ACTION_ADVENTURE
    diff = brief.difficulty or "normal"
    entities: List[DraftEntity] = []
    win: List[DraftWin] = []
    lose: List[DraftLose] = []

    for i, e in enumerate(brief.enemies[:3]):
        default = 6 if genre in (Genre.ARENA_COMBAT, Genre.TOP_DOWN_SHOOTER) else 4
        entities.append(_enemy_entity(e, diff, default if i == 0 else 3))
    if not brief.enemies and not brief.has_guards and genre in (Genre.ARENA_COMBAT, Genre.TOP_DOWN_SHOOTER, Genre.DUNGEON_CRAWLER):
        entities.append(_enemy_entity(NamedThing("enemy", "Enemy"), diff, 5))

    for c in brief.collectibles[:2]:
        default = {Genre.PLATFORMER: 8, Genre.EXPLORATION: 10, Genre.DUNGEON_CRAWLER: 5}.get(genre, 6)
        entities.append(DraftEntity(kind=EntityKind.PICKUP, count=max(1, min(50, c.count or default)), note=c.label[:60],
                                    props={"value": 1}, tags=[f"label:{c.label}"[:40], f"color:{c.color}"]))
    if not brief.collectibles and genre in (Genre.PLATFORMER, Genre.EXPLORATION):
        entities.append(DraftEntity(kind=EntityKind.PICKUP, count=8 if genre == Genre.PLATFORMER else 10, note="Coin",
                                    tags=["label:Coin", "color:#F2C230"]))

    for h in brief.hazards[:2]:
        entities.append(DraftEntity(kind=EntityKind.HAZARD, count=3 if genre != Genre.PLATFORMER else 4, note=h[:60],
                                    props={"damage_per_second": 25.0 * _difficulty_scale(diff)},
                                    tags=[f"label:{h}"[:40]]))
    if brief.has_guards:
        entities.append(DraftEntity(kind=EntityKind.GUARD, count=3 if diff != "hard" else 5, note="Guard",
                                    tags=["label:Guard", "color:#2C3E50"]))
    if brief.has_npc:
        entities.append(DraftEntity(kind=EntityKind.NPC, count=1, note="Quest giver", tags=["label:Quest Giver"]))
    if brief.has_checkpoints or genre == Genre.PLATFORMER:
        entities.append(DraftEntity(kind=EntityKind.CHECKPOINT, count=2, note="Checkpoint"))
    if brief.has_moving_platforms:
        entities.append(DraftEntity(kind=EntityKind.MOVING_PLATFORM, count=3, note="Moving platform"))
    if genre in (Genre.EXPLORATION, Genre.ACTION_ADVENTURE):
        entities.append(DraftEntity(kind=EntityKind.LANDMARK, count=1, note="Landmark"))
    if brief.wants_goal or genre in (Genre.PLATFORMER, Genre.DUNGEON_CRAWLER):
        entities.append(DraftEntity(kind=EntityKind.GOAL, count=1, note=(brief.goal_target or "exit").title()[:60],
                                    tags=[f"label:{(brief.goal_target or 'exit').title()}"[:40]]))
    if genre in (Genre.ARENA_COMBAT, Genre.TOP_DOWN_SHOOTER) and (brief.waves or not brief.survive_seconds):
        waves = max(1, min(50, brief.waves or (3 if diff != "hard" else 5)))
        per_wave = max(2, min(20, (brief.enemies[0].count if brief.enemies and brief.enemies[0].count else 0) // max(1, waves) or
                              {"easy": 3, "normal": 4, "hard": 6}[diff]))
        entities.append(DraftEntity(kind=EntityKind.SPAWNER, count=1, note="Wave spawner",
                                    props={"wave_count": waves, "enemies_per_wave": per_wave,
                                           "seconds_between_waves": 4.0 if diff == "hard" else 6.0}))

    # Win conditions: stated ones first, then genre defaults.
    if brief.survive_seconds:
        win.append(DraftWin(type="survive_seconds", seconds=max(10, min(3600, brief.survive_seconds))))
    if brief.score_target:
        win.append(DraftWin(type="score_at_least", target=max(1, min(10000, brief.score_target))))
    has_pickups = any(e.kind == EntityKind.PICKUP for e in entities)
    has_enemies = any(e.kind in (EntityKind.ENEMY, EntityKind.RANGED_ENEMY) for e in entities)
    has_spawner = any(e.kind == EntityKind.SPAWNER for e in entities)
    stated_collect = bool(brief.collectibles) and bool(re.search(r"\b(collect|gather|find|recover|grab|pick up|steal|loot|rescue|save|retrieve)\b", brief.prompt, re.I))
    if not win:
        if genre in (Genre.ARENA_COMBAT, Genre.TOP_DOWN_SHOOTER) and (has_spawner or has_enemies):
            spawner = next((e for e in entities if e.kind == EntityKind.SPAWNER), None)
            win.append(DraftWin(type="defeat_all", target=int(spawner.props.get("wave_count", 3)) if spawner else None))
        elif genre == Genre.PLATFORMER:
            if stated_collect or has_pickups:
                win.append(DraftWin(type="collect_all"))
            win.append(DraftWin(type="reach_goal"))
        elif genre == Genre.DUNGEON_CRAWLER:
            if stated_collect:
                win.append(DraftWin(type="collect_all"))
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

    # Lose conditions
    if brief.is_board_like:
        lose = [DraftLose(type="match_loss")] if genre == Genre.CARD_BATTLER else [DraftLose(type="board_loss")]
    else:
        # Falling or dying respawns the player at the last checkpoint; dying only *loses* the game when something
        # can actually kill the player (enemies, hazards) or when the prompt gave a number of lives.
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
    if genre == Genre.PLATFORMER or brief.double_jump:
        player_props.setdefault("air_control", 0.45)
    if brief.double_jump:
        player_props["double_jump"] = True
    if brief.sprint:
        player_props["sprint_multiplier"] = 1.8
    if player_props:
        entities.insert(0, DraftEntity(kind=EntityKind.PLAYER, count=1, note="Player", props=player_props))

    size = brief.level_size or ("medium" if genre in (Genre.EXPLORATION, Genre.ACTION_ADVENTURE) else "small")
    pitch = re.sub(r"\s+", " ", brief.prompt).strip()[:280] or f"A {genre.value.replace('_', ' ')} game"
    return DesignDraft(
        title=(brief.title or _synth_title(brief))[:60],
        genre=genre,
        camera=brief.camera or _default_camera(brief),
        pitch=pitch,
        biome=brief.biome,
        lighting=brief.lighting or Lighting.DAY,
        level_size=size,  # type: ignore[arg-type]
        entities=entities[:12],
        win=win[:3],
        lose=lose,
        difficulty=diff,  # type: ignore[arg-type]
        art_style=(brief.art_style or "stylized"),  # type: ignore[arg-type]
        music_mood=brief.music_mood if brief.music_mood in ("none", "calm", "tense", "heroic", "playful") else "none",  # type: ignore[arg-type]
        custom_rules=[],
        questions=[],
    )


def reconcile_draft(draft: DesignDraft, brief: PromptBrief) -> Tuple[DesignDraft, List[str]]:
    """Repairs a model draft so it honours every fact the prompt states. Returns (draft, list of fixes)."""
    fixes: List[str] = []
    data = draft.model_dump()

    # Never let the model drop the user's chosen title, camera or setting.
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

    # Named enemies: ensure each stated enemy type exists with its stated count and label.
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
        elif len(ents) < 12:
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
        elif len(ents) < 12:
            ents.append(DraftEntity(kind=EntityKind.PICKUP, count=max(1, min(50, c.count or 6)), note=c.label[:60],
                                    tags=[f"label:{c.label}"[:40], f"color:{c.color}"]).model_dump())
            kinds.append("pickup")
            fixes.append(f"added missing collectible {c.label}")

    for h in brief.hazards[:2]:
        if not any(k == "hazard" and h.lower() in str(ents[i].get("note", "")).lower() for i, k in enumerate(kinds)) \
                and not (_has(EntityKind.HAZARD) and len(brief.hazards) == 1) and len(ents) < 12:
            ents.append(DraftEntity(kind=EntityKind.HAZARD, count=3, note=h[:60], tags=[f"label:{h}"[:40]]).model_dump())
            kinds.append("hazard")
            fixes.append(f"added missing hazard {h}")
    if brief.has_guards and not _has(EntityKind.GUARD) and len(ents) < 12:
        ents.append(DraftEntity(kind=EntityKind.GUARD, count=3, note="Guard", tags=["label:Guard"]).model_dump())
        kinds.append("guard")
        fixes.append("added guards")
    if brief.has_npc and not _has(EntityKind.NPC) and len(ents) < 12:
        ents.append(DraftEntity(kind=EntityKind.NPC, count=1, note="Quest giver").model_dump())
        kinds.append("npc")
    if brief.wants_goal and not _has(EntityKind.GOAL) and len(ents) < 12 and not brief.is_board_like:
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
        elif len(ents) < 12 and not brief.is_board_like:
            ents.append(DraftEntity(kind=EntityKind.SPAWNER, count=1, note="Wave spawner",
                                    props={"wave_count": brief.waves}).model_dump())
            kinds.append("spawner")
            fixes.append(f"added wave spawner ({brief.waves} waves)")

    # Player facts
    player_props: Dict[str, Any] = {}
    if brief.player_health:
        player_props["max_health"] = float(brief.player_health)
    if brief.lives:
        player_props["lives"] = brief.lives
    if brief.ranged_player is True:
        player_props["attack_mode"] = "projectile"
    elif brief.ranged_player is False:
        player_props["attack_mode"] = "melee"
    if brief.double_jump:
        player_props["double_jump"] = True
    if brief.sprint:
        player_props["sprint_multiplier"] = 1.8
    if player_props:
        pl = next((e for e, k in zip(ents, kinds) if k == "player"), None)
        if pl is None and len(ents) < 12:
            ents.insert(0, DraftEntity(kind=EntityKind.PLAYER, count=1, note="Player", props=player_props).model_dump())
        elif pl is not None:
            props = dict(pl.get("props") or {})
            props.update(player_props)
            pl["props"] = props
    data["entities"] = ents[:12]

    # Win / lose facts
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
            w["target"] = None   # always "all of them": the count lives on the pickup entity
    data["win"] = wins[:3] or [{"type": "reach_goal", "target": None, "seconds": None}]
    loses = list(data.get("lose") or [])
    ltypes = {str(lz["type"]) for lz in loses}
    if brief.time_limit_seconds and "timer_runs_out" not in ltypes and len(loses) < 3:
        loses.append({"type": "timer_runs_out", "seconds": brief.time_limit_seconds, "target": None})
        fixes.append(f"lose: time limit {brief.time_limit_seconds}s")
    if brief.has_guards and "caught_by_guard" not in ltypes and len(loses) < 3:
        loses.append({"type": "caught_by_guard", "seconds": None, "target": None})
    data["lose"] = loses[:3]
    data["questions"] = []   # facts were reconciled; do not block the build on model questions

    try:
        return DesignDraft.model_validate(data), fixes
    except Exception as exc:  # never make a valid draft worse
        return draft, [f"reconciliation skipped: {exc}"]


def brief_for_model(brief: PromptBrief) -> str:
    lines = brief.summary_lines()
    if not lines:
        return ""
    return ("Facts stated in the user's prompt (your JSON MUST keep every one of these; use the given names in "
            "entity notes and the given counts):\n- " + "\n- ".join(lines))
