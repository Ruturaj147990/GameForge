"""AI Intent Analysis & Prompt Classification for GameForge 1.0 (P1/P9).

Provides robust classification of user prompts into:
- GAME_CREATION: User desires to author a new game from scratch.
- GAME_MUTATION: User desires to edit, modify, tune, or balance an existing game.
- CONVERSATIONAL: Pleasantries, greetings, assistant identity inquiries, small talk.
- INFORMATIONAL: Questions about game design, mechanics, Unreal Engine, coding concepts.
- CODE_OR_DEBUG: Error fixing, debugging, compile repair, refactoring.

Eliminates template hijacking, conversational false-positives, typo failures,
and handles comprehensive modern genre mapping.
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


# Typo normalization map for common user misspellings
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

# Verbs signaling game creation intent
CREATE_VERB_PAT = re.compile(
    r"\b(create|make|build|generate|develop|design|give me|gimme|i want|wanna|want|need|"
    r"write|complete|finish|expand|build out|author|code|implement|deploy|construct|produce|"
    r"craft|scaffold|spin up|whip up|put together|start|program|setup|set up)\b",
    re.I,
)

# Standalone game words
GAME_WORD_PAT = re.compile(
    r"(?<![\w/\\.])(?:games?|gem|gaem|gme|gmes|gam|shtr|brawler|vidya|title)\b(?!\s*(?:mode|state|instance|play|object|loop|class)\b)(?![\w/\\.])",
    re.I,
)

# Create game phrase: "create a ... game"
CREATE_GAME_PAT = re.compile(
    r"\b(?:create|make|build|generate|develop|design|write|give me|gimme|i want|wanna|want|need|"
    r"complete|finish|expand|build out|author|code|implement|deploy|construct|produce|craft|"
    r"scaffold|spin up|whip up|put together)\s+(?:me\s+)?"
    r"(?:[\w\-\']+\s+){0,8}?(?:games?|title)\b(?!\s*(?:mode|state|instance|play|object)\b)",
    re.I,
)

# Noun phrase game: "a 3D platformer game with 5 coins"
NOUN_GAME_PAT = re.compile(
    r"^(?:(?:a|an|the)\s+)?(?:[\w\-\']+\s+){0,8}(?:games?|title)"
    r"(?:\s+(?:with|where|featuring|set in|having)\b.*)?$",
    re.I,
)

# Conversational greetings and polite lead-ins
GREETING_PREFIX_PAT = re.compile(
    r"^(?:(?:hi|hello|hey|howdy|good\s+(?:morning|afternoon|evening|day)|greetings|"
    r"please|pls|can\s+you(?:\s+please)?|could\s+you(?:\s+please)?|would\s+you(?:\s+please)?|"
    r"i\s+(?:was\s+wondering\s+if\s+you\s+could|would\s+like\s+to\s+know\s+if\s+you\s+can|"
    r"wanted\s+to\s+ask\s+if\s+you\s+can)|do\s+you\s+know|can\s+i\s+ask|"
    r"so|well|okay|alright|yo)\s*[,!?:;]*\s*)+",
    re.I,
)

# Pure small talk / conversational phrases
PURE_CONVERSATIONAL_PAT = re.compile(
    r"^(?:hello|hi|hey|howdy|good\s+(?:morning|afternoon|evening)|greetings|"
    r"who\s+are\s+you|what\s+are\s+you|what\s+is\s+your\s+name|what\s+can\s+you\s+do|"
    r"how\s+are\s+you|how's\s+it\s+going|what's\s+up|help|help\s+me|"
    r"thank\s+you|thanks|thx|bye|goodbye|see\s+ya)$",
    re.I,
)

# Informational / conceptual questions
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

# Work inside existing game or code
EXISTING_GAME_CONTEXT_PAT = re.compile(
    r"\b(?:for|in|into|inside|of|to)\s+(?:my|the|this|our|your)\s+games?\b",
    re.I,
)

# Bug/debug/refactoring indicators
CODE_DEBUG_PAT = re.compile(
    r"\b(?:fix|debug|error|bug|issue|problem|refactor|compile|build error|crash|failed assertion|"
    r"stack trace|nullptr|null pointer|memory leak|syntax error|warning|unresolved external)\b",
    re.I,
)

# Documentation/analysis indicators
DOC_ANALYSIS_PAT = re.compile(
    r"\b(?:analysis|essay|article|overview|document|lore|story|script|breakdown|history|"
    r"historical|gameplay loop|progression curve|whitepaper|design document|gdd)\b",
    re.I,
)

# Modern genres and subgenres mapping
GENRE_PATTERNS: List[Tuple[Genre, re.Pattern]] = [
    (Genre.GRID_BOARD, re.compile(r"\b(?:grid\s+board|board\s+game|tic[- ]tac[- ]toe|tictactoe|connect\s+(?:four|4)|four\s+in\s+a\s+row|gomoku|five\s+in\s+a\s+row|snakes?\s+and\s+ladders?|chutes\s+and\s+ladders?|ludo|chess|checkers|parcheesi|monopoly|dice\s+board|roll\s+and\s+move)\b", re.I)),
    (Genre.CARD_BATTLER, re.compile(r"\b(?:card\s+battler|card\s+game|deck\s*builder|deck\s*building|card\s+battle|deck\s+battler|lane\s+battler|collectible\s+card|tcg|ccg|hearthstone|slay\s+the\s+spire|balatro)\b", re.I)),
    (Genre.TOP_DOWN_SHOOTER, re.compile(r"\b(?:top[- ]down\s+shooter|topdown\s+shooter|twin[- ]stick\s+shooter|arena\s+shooter|shmup|shoot\s*'?em\s*up|bullet\s+hell|danmaku)\b", re.I)),
    (Genre.ARENA_COMBAT, re.compile(r"\b(?:arena\s+combat|combat\s+arena|gladiator\s+arena|wave\s+combat|action\s+arena|brawler|beat\s*'?em\s*up|hack\s+and\s+slash)\b", re.I)),
    (Genre.PLATFORMER, re.compile(r"\b(?:platformer|3d\s+platformer|2d\s+platformer|jump\s+and\s+run|jumping\s+game|platform\s+game|parkour|speedrun\s+platformer|endless\s+runner|runner\s+game)\b", re.I)),
    (Genre.DUNGEON_CRAWLER, re.compile(r"\b(?:dungeon\s+crawler|dungeon\s+crawl|roguelike|roguelite|arpg|action\s+rpg|diablo|binding\s+of\s+isaac|enter\s+the\s+gungeon)\b", re.I)),
    (Genre.EXPLORATION, re.compile(r"\b(?:exploration|open\s+world|procedural\s+world|procedural\s+landscape|terrain\s+generation|hiking\s+trail|survival\s+craft|walking\s+simulator|sandbox)\b", re.I)),
    (Genre.ACTION_ADVENTURE, re.compile(r"\b(?:action\s+adventure|relic\s+hunt|adventure\s+game|quest|souls[- ]like|soulslike|metroidvania|stealth\s+adventure|third[- ]person\s+shooter)\b", re.I)),
    (Genre.PUZZLE, re.compile(r"\b(?:puzzle\s+game|logic\s+puzzle|escape\s+room|physics\s+puzzle|match\s+3|sokoban|block\s+puzzle)\b", re.I)),
]

# Common gameplay mechanics keywords
MECHANIC_KEYWORDS: Set[str] = {
    "dash", "grapple", "grappling", "hookshot", "jetpack", "slide", "sliding", "walljump", "wall-jump",
    "double-jump", "double jump", "triple-jump", "climb", "climbing", "glide", "gliding", "swim", "swimming",
    "fly", "flying", "sprint", "sprinting", "crouch", "crouching", "sneak", "sneaking", "stealth",
    "shield", "shields", "mana", "stamina", "energy", "spell", "spells", "magic", "skill", "skills",
    "ability", "abilities", "perk", "perks", "talent", "talents", "combo", "parry", "parrying",
    "dodge", "dodging", "roll", "rolling", "block", "blocking", "bow", "arrow", "arrows",
    "sword", "swords", "blade", "axe", "hammer", "dagger", "spear", "rifle", "shotgun", "pistol",
    "grenade", "inventory", "craft", "crafting", "loot", "looting", "chest", "shop", "merchant",
    "upgrade", "upgrades", "level up", "xp", "experience", "boss", "bosses", "minion", "trap",
    "traps", "hazard", "puzzle", "riddle", "checkpoint", "timer", "countdown", "permadeath",
}


def normalize_prompt(prompt: str) -> str:
    """Normalize whitespace, quotes, and common misspellings in user prompts."""
    text = (prompt or "").strip().replace("’", "'").replace("“", '"').replace("”", '"')
    # Word-level typo replacement
    for typo, correction in TYPO_REPLACEMENTS.items():
        pattern = r"\b" + re.escape(typo) + r"\b"
        text = re.sub(pattern, correction, text, flags=re.I)
    return text


def strip_conversational_prefixes(prompt: str) -> str:
    """Strip leading conversational greetings and polite requests."""
    text = prompt.strip()
    return GREETING_PREFIX_PAT.sub("", text).strip()


def is_game_creation_request(prompt: str) -> bool:
    """Determine whether a natural-language prompt is a request to author a game.

    Handles leading greetings, conversational questions, bug/edit requests,
    typos, and modern game genres.
    """
    if not prompt or not prompt.strip():
        return False

    normalized = normalize_prompt(prompt)
    stripped = strip_conversational_prefixes(normalized)
    text = stripped.lower().strip()

    # 1. Pure conversational check on raw / stripped prompt
    raw_lower = normalized.lower().strip().rstrip(".!?")
    if PURE_CONVERSATIONAL_PAT.match(raw_lower) or (text and PURE_CONVERSATIONAL_PAT.match(text.rstrip(".!?"))):
        return False

    # 2. Informational questions & project status/completeness inquiries:
    # e.g., "what is a platformer", "is the sudoku game complete", "status of the build"
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

    # 3. Bug fixes, refactoring, code editing, Unreal source files
    if CODE_DEBUG_PAT.search(text):
        return False
    if re.search(r"(?:\.uproject|\.cpp|\.h|\.ini|\bSource/|\bclass\b|\bstruct\b)", text, re.I):
        return False
    if re.search(r"\b(?:game\s+(?:mode|state|instance|object|loop)|gamemode)\b", text, re.I) and not CREATE_GAME_PAT.search(text):
        return False

    # 4. Context inside an existing game or documentation analysis
    if EXISTING_GAME_CONTEXT_PAT.search(text):
        return False
    if DOC_ANALYSIS_PAT.search(text) and not any(v in text for v in ("make", "create", "build", "design")):
        return False

    # 5. Direct game creation patterns
    if CREATE_GAME_PAT.search(text):
        return True
    if NOUN_GAME_PAT.match(text):
        return True
    if ":" in text and GAME_WORD_PAT.search(text):
        return True

    # 6. Specific board games standalone
    clean_text = text.replace("-", " ").strip()
    if clean_text in (
        "monopoly", "chess", "checkers", "gomoku", "ludo", "parcheesi",
        "snakes and ladders", "snake and ladders", "chutes and ladders",
        "connect four", "tic tac toe",
    ):
        return True

    # 7. Comprehensive modern genres check
    genre_match = False
    for _, pattern in GENRE_PATTERNS:
        if pattern.search(text):
            genre_match = True
            break

    if not genre_match:
        # Check additional standalone genre tags
        if re.search(
            r"\b(?:clone|fps|shooter|adventure|rpg|roguelike|roguelite|counterstrike|counter-strike|"
            r"brawler|stealth|dungeon|survival|horror|arena|card\s+battler|board\s+game|tactical|"
            r"snake|ladders|chutes|ludo|chess|checkers|monopoly|dice\s+board|runner|racing|racer|"
            r"simulator|sim|strategy|rts|tbs|defense|tower\s+defense|puzzle|escape|flight|dogfight|"
            r"combat|action|brawl|metroidvania|sandbox|open\s+world|quest|autobattler|auto\s+battler|"
            r"shmup|bullet\s+hell|souls[- ]like|soulslike|deckbuilder|battle\s+royale|moba|arpg|jrpg|"
            r"crpg|mmorpg|visual\s+novel|clicker|idle\s+game|cozy\s+game|twin[- ]stick)\b",
            text,
        ):
            genre_match = True

    if genre_match:
        if (
            CREATE_VERB_PAT.search(text)
            or GAME_WORD_PAT.search(text)
            or text.startswith(("a ", "an ", "the ", "deploy ", "construct "))
            or ":" in text
        ):
            return True

    # 8. Create verb plus game keywords or recipes
    if CREATE_VERB_PAT.search(text):
        if GAME_WORD_PAT.search(text):
            return True
        try:
            from .presets import PRESET_KEYWORDS
            if any(k in text for kws in PRESET_KEYWORDS.values() for k in kws):
                return True
        except ImportError:
            pass

    return False


def detect_genre_intent(prompt: str) -> Optional[Genre]:
    """Detect the most likely Genre enum from prompt text, prioritizing dominant main clause over subordinate modifiers."""
    normalized = normalize_prompt(prompt).lower()
    # 1. Main clause check (before secondary modifiers like 'with giant chess tiles' or 'featuring card mini-game')
    main_clause = re.split(r"\b(?:with|featuring|where|having|set in|containing|on giant|on a)\b", normalized, maxsplit=1)[0].strip()
    if main_clause:
        for genre, pattern in GENRE_PATTERNS:
            if pattern.search(main_clause):
                return genre

    # 2. Full prompt fallback
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
            # Check if this mechanic is negated (e.g. "no timer", "without hazards", "never jump")
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

    # Conversational
    if not text or PURE_CONVERSATIONAL_PAT.match(raw_lower) or (text and PURE_CONVERSATIONAL_PAT.match(text.rstrip(".!?"))):
        return IntentResult(
            intent=IntentType.CONVERSATIONAL,
            confidence=0.95,
            is_creation=False,
            normalized_prompt=norm,
            reasons=["Prompt matches pure conversational greeting or small-talk pattern"],
        )

    # Informational
    if INFORMATIONAL_QUESTION_PAT.search(text) or (norm.lower().startswith(("what", "how", "why", "who", "explain")) and "?" in norm):
        return IntentResult(
            intent=IntentType.INFORMATIONAL,
            confidence=0.90,
            is_creation=False,
            normalized_prompt=norm,
            reasons=["Prompt matches informational question or inquiry pattern"],
        )

    # Code / Debug
    if CODE_DEBUG_PAT.search(text):
        return IntentResult(
            intent=IntentType.CODE_OR_DEBUG,
            confidence=0.85,
            is_creation=False,
            normalized_prompt=norm,
            reasons=["Prompt specifies bug fix, compile error, or code debugging"],
        )

    # Mutation vs Creation
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
            reasons=["Prompt specifies game creation verbs, genre keywords, or game specifications"],
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
