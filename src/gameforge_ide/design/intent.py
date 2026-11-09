"""AI Intent Analysis & Prompt Classification for GameForge 1.0 (P1/P9).

Provides robust classification of user prompts into:
- GAME_CREATION: User desires to author a new game from a natural-language prompt.
- GAME_MUTATION: User desires to edit, modify, tune, or balance an existing game.
- CONVERSATIONAL: Pleasantries, greetings, assistant identity inquiries, small talk.
- INFORMATIONAL: Questions about game design, mechanics, Unreal Engine, coding concepts.
- CODE_OR_DEBUG: Error fixing, debugging, compile repair, refactoring.

Eliminates template hijacking, conversational false-positives, typo failures,
and handles arbitrary novel game concepts and mechanics.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from .gds import Genre


class IntentType(str, Enum):
    GAME_CREATION = "game_creation"
    GAME_MUTATION = "game_mutation"
    CONVERSATIONAL = "conversational"
    INFORMATIONAL = "informational"
    CODE_OR_DEBUG = "code_or_debug"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    intent: IntentType
    confidence: float
    is_creation: bool
    genre: Optional[Genre] = None
    mechanics: List[str] = field(default_factory=list)
    normalized_prompt: str = ""
    reasons: List[str] = field(default_factory=list)


TYPO_REPLACEMENTS: Dict[str, str] = {
    "buid": "build",
    "biuld": "build",
    "buiild": "build",
    "craete": "create",
    "creat": "create",
    "creaet": "create",
    "crte": "create",
    "mak": "make",
    "mkae": "make",
    "maek": "make",
    "platfomer": "platformer",
    "platfromer": "platformer",
    "platforer": "platformer",
    "rouguelike": "roguelike",
    "rougelike": "roguelike",
    "rouge-like": "roguelike",
    "rouge like": "roguelike",
    "tower defence": "tower defense",
    "gaem": "game",
    "gem": "game",
    "gme": "game",
    "gmes": "games",
    "shtr": "shooter",
}

CREATE_VERB_PAT = re.compile(
    r"\b(create|make|build|generate|develop|design|give me|gimme|i want|wanna|want|need|"
    r"write|complete|finish|expand|build out|author|code|implement|deploy|construct|produce|"
    r"craft|scaffold|spin up|whip up|put together|start|program|setup|set up)\b",
    re.I,
)

GAME_WORD_PAT = re.compile(
    r"(?<![\w/\\.])(?:games?|gem|gaem|gme|gmes|gam|shtr|brawler|vidya|title|mission|simulation|experience|adventure|challenge)\b(?!\s*(?:mode|state|instance|play|object|loop|class)\b)(?![\w/\\.])",
    re.I,
)

CREATE_GAME_PAT = re.compile(
    r"\b(?:create|make|build|generate|develop|design|write|give me|gimme|i want|wanna|want|need|"
    r"complete|finish|expand|build out|author|code|implement|deploy|construct|produce|craft|"
    r"scaffold|spin up|whip up|put together)\s+(?:me\s+)?"
    r"(?:[\w\-\']+\s+){0,10}?(?:games?|title|mission|adventure|simulation|prototype|level)\b(?!\s*(?:mode|state|instance|play|object)\b)",
    re.I,
)

NOUN_GAME_PAT = re.compile(
    r"^(?:(?:a|an|the)\s+)?(?:[\w\-\']+\s+){0,10}(?:games?|title|mission|adventure|simulation)"
    r"(?:\s+(?:with|where|featuring|set in|having|in which)\b.*)?$",
    re.I,
)

# Structural gameplay descriptors that indicate a prompt is describing a playable game even if it omits the literal word "game"
GAMEPLAY_STRUCTURE_PAT = re.compile(
    r"\b(?:where\s+(?:you|the\s+player)|collect(?:ing)?\s+\d+|dodge|dodging|survive|surviving|defeat(?:ing)?|"
    r"defend(?:ing)?|waves?\s+of|patrol(?:ling)?\s+guards?|reach\s+the\s+(?:exit|goal|portal|beacon|summit|finish)|"
    r"time\s+limit|health|stamina|mana|oxygen|shield|turrets?|checkpoints?|laps?|obstacles?|hazards?|"
    r"first[- ]person|third[- ]person|top[- ]down|side[- ]scroller)\b",
    re.I,
)

GREETING_PREFIX_PAT = re.compile(
    r"^(?:(?:hi|hello|hey|howdy|good\s+(?:morning|afternoon|evening|day)|greetings|"
    r"please|pls|can\s+you(?:\s+please)?|could\s+you(?:\s+please)?|would\s+you(?:\s+please)?|"
    r"i\s+(?:was\s+wondering\s+if\s+you\s+could|would\s+like\s+to\s+know\s+if\s+you\s+can|"
    r"wanted\s+to\s+ask\s+if\s+you\s+can)|do\s+you\s+know|can\s+i\s+ask|"
    r"so|well|okay|alright|yo)\s*[,!?:;]*\s*)+",
    re.I,
)

PURE_CONVERSATIONAL_PAT = re.compile(
    r"^(?:hello|hi|hey|howdy|good\s+(?:morning|afternoon|evening)|greetings|"
    r"who\s+are\s+you|what\s+are\s+you|what\s+is\s+your\s+name|what\s+can\s+you\s+do|"
    r"how\s+are\s+you|how's\s+it\s+going|what's\s+up|help|help\s+me|"
    r"thank\s+you|thanks|thx|bye|goodbye|see\s+ya)$",
    re.I,
)

INFORMATIONAL_QUESTION_PAT = re.compile(
    r"^(?:what\s+(?:is|was|are|were|do|does|a|an|the)|how\s+(?:to|do|can|does|did|is|are|would)|"
    r"why\s+(?:is|was|are|were|do|does|did|would)|who\s+(?:is|was|are|were|made|created|invented|built|developed|designed|authored)|"
    r"which\s+(?:is|was|are|games?)|where\s+(?:is|was|are|can|do)|"
    r"explain\b|describe\b|tell\s+me\s+(?:about|the\s+difference|how|what|why|who|if|whether)|about\b|"
    r"remind\s+me\b|what's\s+the\s+difference|can\s+you\s+explain|give\s+me\s+an\s+overview|"
    r"history\s+of\b|guide\s+on\b|any\s+(?:[\w\-]+\s+){0,3}(?:games?|titles?)|"
    r"is\s+there\b|are\s+there\b|do\s+you\s+have\b)",
    re.I,
)

EXISTING_GAME_CONTEXT_PAT = re.compile(
    r"\b(?:for|in|into|inside|of|to)\s+(?:my|the|this|our|your)\s+games?\b",
    re.I,
)

CODE_DEBUG_PAT = re.compile(
    r"\b(?:fix|debug|error|bug|issue|problem|refactor|compile|build error|crash|failed assertion|"
    r"stack trace|nullptr|null pointer|memory leak|syntax error|warning|unresolved external)\b",
    re.I,
)

DOC_ANALYSIS_PAT = re.compile(
    r"\b(?:analysis|essay|article|overview|document|lore|story|script|breakdown|history|"
    r"historical|gameplay loop|progression curve|whitepaper|design document|gdd)\b",
    re.I,
)

GENRE_PATTERNS: List[Tuple[Genre, re.Pattern]] = [
    (Genre.GRID_BOARD, re.compile(r"\b(?:grid\s+board|board\s+game|tic[- ]tac[- ]toe|tictactoe|noughts\s+(?:and|&)\s+crosses|connect\s+(?:four|4)|four\s+in\s+a\s+row|gomoku|five\s+in\s+a\s+row|roll\s+and\s+move|dice\s+board|turn[- ]based\s+board|strategy\s+board|checkers|draughts|chess)\b", re.I)),
    (Genre.CARD_BATTLER, re.compile(r"\b(?:card\s+battler|card\s+game|deck\s*builder|deck\s*building|card\s+battle|deck\s+battler|lane\s+battler|collectible\s+card|tcg|ccg)\b", re.I)),
    (Genre.TOP_DOWN_SHOOTER, re.compile(r"\b(?:top[- ]down\s+shooter|topdown\s+shooter|twin[- ]stick\s+shooter|arena\s+shooter|shmup|shoot\s*'?em\s*up|bullet\s+hell|danmaku)\b", re.I)),
    (Genre.ARENA_COMBAT, re.compile(r"\b(?:arena\s+combat|combat\s+arena|gladiator\s+arena|wave\s+combat|action\s+arena|brawler|beat\s*'?em\s*up|hack\s+and\s+slash|wave\s+survival|horde\s+survival|survival\s+arena|tower\s+defense|defend\s+the\s+(?:base|core|nexus)|turret\s+defense|bomb\s+defusal|tactical\s+shooter|fps\s+arena)\b", re.I)),
    (Genre.PLATFORMER, re.compile(r"\b(?:platformer|3d\s+platformer|2d\s+platformer|jump\s+and\s+run|jumping\s+game|platform\s+game|parkour|speedrun\s+platformer|endless\s+runner|runner\s+game|racing|racer|race\s+track|kart\s+racer|time\s+trial|obstacle\s+course)\b", re.I)),
    (Genre.DUNGEON_CRAWLER, re.compile(r"\b(?:dungeon\s+crawler|dungeon\s+crawl|roguelike|roguelite|arpg|action\s+rpg|infiltration|heist|stealth\s+mission)\b", re.I)),
    (Genre.EXPLORATION, re.compile(r"\b(?:exploration|open\s+world|procedural\s+world|procedural\s+landscape|procedural\s+terrain|procedural\s+environment|terrain\s+generation|hiking\s+trail|survival\s+craft|walking\s+simulator|sandbox|salvage\s+mission|expedition)\b", re.I)),
    (Genre.ACTION_ADVENTURE, re.compile(r"\b(?:action\s+adventure|relic\s+hunt|adventure\s+game|quest|souls[- ]like|soulslike|metroidvania|stealth\s+adventure|third[- ]person\s+shooter)\b", re.I)),
    (Genre.PUZZLE, re.compile(r"\b(?:puzzle\s+game|logic\s+puzzle|escape\s+room|physics\s+puzzle|match\s+3|sokoban|block\s+puzzle|number\s+puzzle|grid\s+puzzle|constraint\s+puzzle|falling\s+blocks|mine\s+deduction|snake(?:\s+game)?|sudoku|tetris)\b", re.I)),
]

MECHANIC_KEYWORDS: Set[str] = {
    "dash", "grapple", "grappling", "hookshot", "jetpack", "slide", "sliding", "walljump", "wall-jump", "wall jump",
    "double-jump", "double jump", "triple-jump", "climb", "climbing", "glide", "gliding", "swim", "swimming",
    "fly", "flying", "sprint", "sprinting", "crouch", "crouching", "sneak", "sneaking", "stealth", "patrol",
    "shield", "shields", "mana", "stamina", "energy", "oxygen", "heat", "spell", "spells", "magic", "skill", "skills",
    "ability", "abilities", "perk", "perks", "talent", "talents", "combo", "parry", "parrying",
    "dodge", "dodging", "roll", "rolling", "block", "blocking", "bow", "arrow", "arrows",
    "sword", "swords", "blade", "axe", "hammer", "dagger", "spear", "rifle", "shotgun", "pistol", "sniper", "laser",
    "grenade", "inventory", "craft", "crafting", "loot", "looting", "chest", "shop", "merchant",
    "upgrade", "upgrades", "level up", "xp", "experience", "boss", "bosses", "minion", "trap",
    "traps", "hazard", "puzzle", "riddle", "checkpoint", "timer", "countdown", "permadeath",
    "turret", "tower", "wave", "waves", "lap", "laps", "drift", "boost", "nitro", "vehicle", "driving",
    "quest", "dialogue", "defuse", "plant", "portal", "teleporter", "synergy", "relic", "hack", "switch", "door",
}


def normalize_prompt(prompt: str) -> str:
    """Normalize whitespace, quotes, and common misspellings in user prompts."""
    text = (prompt or "").strip().replace("’", "'").replace("“", '"').replace("”", '"')
    for typo, correction in TYPO_REPLACEMENTS.items():
        pattern = r"\b" + re.escape(typo) + r"\b"
        text = re.sub(pattern, correction, text, flags=re.I)
    return text


def strip_conversational_prefixes(prompt: str) -> str:
    """Strip leading conversational greetings and polite requests."""
    text = prompt.strip()
    return GREETING_PREFIX_PAT.sub("", text).strip()


def is_game_creation_request(prompt: str) -> bool:
    """Determine whether a natural-language prompt is a request to author a game."""
    if not prompt or not prompt.strip():
        return False

    normalized = normalize_prompt(prompt)
    stripped = strip_conversational_prefixes(normalized)
    text = stripped.lower().strip()

    raw_lower = normalized.lower().strip().rstrip(".!?")
    if PURE_CONVERSATIONAL_PAT.match(raw_lower) or (text and PURE_CONVERSATIONAL_PAT.match(text.rstrip(".!?"))):
        return False

    if INFORMATIONAL_QUESTION_PAT.search(text):
        return False
    orig_lower = normalized.lower().strip()
    question_starters = (
        "what", "how", "why", "who", "is", "are", "can", "could", "should",
        "would", "does", "did", "has", "have", "was", "were", "check", "verify", "status",
    )
    is_status_query = bool(re.search(
        r"\b(?:complete|completed|done|finished|ready|status|progress|state|exist|existing|working|built|packaged|errors?|issues?|logs?)\b",
        orig_lower,
    ))
    if orig_lower.startswith(question_starters) and is_status_query and not re.search(r"\b(create|make|build|scaffold|generate|author)\b", orig_lower):
        return False

    if orig_lower.startswith(("what", "how", "why", "who", "explain", "tell me", "remind me")) and "?" in orig_lower:
        return False
    if (text.endswith("?") or "?" in orig_lower) and not re.search(r"\b(create|make|build|generate|develop|scaffold|craft)\b", text):
        return False

    if CODE_DEBUG_PAT.search(text):
        return False
    if re.search(r"(?:\.uproject|\.cpp|\.h|\.ini|\bSource/|\bclass\b|\bstruct\b)", text, re.I):
        return False
    if re.search(r"\b(?:game\s+(?:mode|state|instance|object|loop)|gamemode)\b", text, re.I) and not CREATE_GAME_PAT.search(text):
        return False

    if EXISTING_GAME_CONTEXT_PAT.search(text):
        return False
    if DOC_ANALYSIS_PAT.search(text) and not any(v in text for v in ("make", "create", "build", "design")):
        return False

    if re.search(r"\bpreset:[a-z0-9_]+\b", text, re.I):
        return True

    if CREATE_GAME_PAT.search(text):
        return True
    if NOUN_GAME_PAT.match(text):
        return True
    if ":" in text and GAME_WORD_PAT.search(text):
        return True

    # Standalone genre/archetype short prompts
    clean_text = text.replace("-", " ").strip()
    if clean_text in (
        "platformer", "3d platformer", "arena combat", "card battler", "top down shooter",
        "relic hunt", "procedural world", "dungeon crawler", "tower defense", "racing",
        "tic tac toe", "connect four", "connect 4", "gomoku", "board game", "puzzle game",
        "chess", "checkers", "sudoku", "tetris", "minesweeper", "roguelike",
    ):
        return True

    genre_match = any(pattern.search(text) for _, pattern in GENRE_PATTERNS)
    if not genre_match:
        if re.search(
            r"\b(?:clone|fps|shooter|adventure|rpg|roguelike|roguelite|"
            r"brawler|stealth|dungeon|survival|horror|arena|card\s+battler|board\s+game|tactical|"
            r"dice\s+board|runner|racing|racer|heist|infiltration|salvage|"
            r"simulator|sim|strategy|rts|tbs|defense|tower\s+defense|puzzle|escape|flight|dogfight|"
            r"combat|action|brawl|metroidvania|sandbox|open\s+world|quest|autobattler|auto\s+battler|"
            r"shmup|bullet\s+hell|souls[- ]like|soulslike|deckbuilder|battle\s+royale|moba|arpg|jrpg|"
            r"crpg|mmorpg|visual\s+novel|clicker|idle\s+game|cozy\s+game|twin[- ]stick)\b",
            text,
        ):
            genre_match = True

    if genre_match and (
        CREATE_VERB_PAT.search(text)
        or GAME_WORD_PAT.search(text)
        or GAMEPLAY_STRUCTURE_PAT.search(text)
        or text.startswith(("a ", "an ", "the ", "deploy ", "construct "))
        or ":" in text
    ):
        return True

    if CREATE_VERB_PAT.search(text) and (GAME_WORD_PAT.search(text) or GAMEPLAY_STRUCTURE_PAT.search(text)):
        return True

    if text.startswith(("a ", "an ")) and GAMEPLAY_STRUCTURE_PAT.search(text) and len(text.split()) >= 6:
        return True

    return False


def detect_genre_intent(prompt: str) -> Optional[Genre]:
    """Detect the most likely Genre enum from prompt text, prioritizing dominant main clause over subordinate modifiers."""
    normalized = normalize_prompt(prompt).lower()
    main_clause = re.split(r"\b(?:with|featuring|where|having|set in|containing|on giant|on a)\b", normalized, maxsplit=1)[0].strip()
    if main_clause:
        for genre, pattern in GENRE_PATTERNS:
            if pattern.search(main_clause):
                return genre

    for genre, pattern in GENRE_PATTERNS:
        if pattern.search(normalized):
            return genre
    return None


def extract_gameplay_mechanics(prompt: str) -> List[str]:
    """Extract recognized custom gameplay mechanics mentioned in the prompt, respecting negative constraints."""
    normalized = normalize_prompt(prompt).lower()
    words = set(re.findall(r"\b[\w\-]+\b", normalized))
    found: List[str] = []
    for m in sorted(MECHANIC_KEYWORDS):
        if m in words or (" " in m and m in normalized):
            is_negated = bool(re.search(rf"\b(?:no|without|zero|never|no\s+more|remove)\s+(?:[\w\-]+\s+)?{re.escape(m)}\b", normalized))
            if not is_negated:
                found.append(m)
    return found


def classify_prompt_intent(prompt: str) -> IntentResult:
    """Perform comprehensive intent analysis on a prompt."""
    norm = normalize_prompt(prompt)
    stripped = strip_conversational_prefixes(norm)
    text = stripped.lower().strip()
    raw_lower = norm.lower().strip().rstrip(".!?")

    if not text or PURE_CONVERSATIONAL_PAT.match(raw_lower) or (text and PURE_CONVERSATIONAL_PAT.match(text.rstrip(".!?"))):
        return IntentResult(
            intent=IntentType.CONVERSATIONAL,
            confidence=0.95,
            is_creation=False,
            normalized_prompt=norm,
            reasons=["Prompt matches pure conversational greeting or small-talk pattern"],
        )

    if INFORMATIONAL_QUESTION_PAT.search(text) or (norm.lower().startswith(("what", "how", "why", "who", "explain")) and "?" in norm):
        return IntentResult(
            intent=IntentType.INFORMATIONAL,
            confidence=0.90,
            is_creation=False,
            normalized_prompt=norm,
            reasons=["Prompt matches informational question or inquiry pattern"],
        )

    if CODE_DEBUG_PAT.search(text):
        return IntentResult(
            intent=IntentType.CODE_OR_DEBUG,
            confidence=0.85,
            is_creation=False,
            normalized_prompt=norm,
            reasons=["Prompt specifies bug fix, compile error, or code debugging"],
        )

    genre = detect_genre_intent(norm)
    mechanics = extract_gameplay_mechanics(norm)

    if EXISTING_GAME_CONTEXT_PAT.search(text):
        return IntentResult(
            intent=IntentType.GAME_MUTATION,
            confidence=0.85,
            is_creation=False,
            genre=genre,
            mechanics=mechanics,
            normalized_prompt=norm,
            reasons=["Prompt specifies modifications inside an existing game"],
        )

    is_creation = is_game_creation_request(prompt)
    if is_creation:
        return IntentResult(
            intent=IntentType.GAME_CREATION,
            confidence=0.92,
            is_creation=True,
            genre=genre,
            mechanics=mechanics,
            normalized_prompt=norm,
            reasons=["Prompt specifies game creation verbs, genre keywords, or gameplay specifications"],
        )

    return IntentResult(
        intent=IntentType.UNKNOWN,
        confidence=0.50,
        is_creation=False,
        genre=genre,
        mechanics=mechanics,
        normalized_prompt=norm,
        reasons=["Prompt did not match creation, conversational, informational, or debug patterns"],
    )
