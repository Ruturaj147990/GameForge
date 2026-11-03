# GameForge — Prompt-to-GDS Pipeline Audit & Architecture Analysis

**Audit Date:** 2026-11-03T14:00:00Z  
**Investigator:** Antigravity Autonomous Inspector & Remediation Agent  
**Status:** COMPLETE & VERIFIED  

---

## 1. Executive Summary

A comprehensive investigation was conducted into GameForge's prompt-to-GDS generation pipeline following an incident where the natural language prompt:
```
"make a snake and ladders game"
```
unexpectedly produced:
- `genre: Platformer`
- `camera: top_down`
- `players: 1`
- `pitch: [Yes] [No]` (malformed/placeholder text)
- Level scene with generic platforms, cubes, and mannequin.

This audit establishes the root causes across each stage of prompt interpretation, taxonomy mapping, preset extraction, model prompting, and draft expansion.

---

## 2. Root Cause Analysis

### 2.1 Keyword Preset Matching Absence
In `src/gameforge_ide/design/presets.py`, `PRESET_KEYWORDS` defined keyword mappings for:
- `tic_tac_toe` (`["tic tac toe", "tictactoe", "noughts and crosses", ...]`)
- `connect_four` (`["four in a row", "connect four", ...]`)
- `gomoku` (`["gomoku", "five in a row", ...]`)
- `platformer` (`["platformer", "3d platformer", "jump and run", "jumping game", "parkour"]`)
- `arena_combat` (`["arena combat", "gladiator", "wave combat", "brawler"]`)
- `card_battler` (`["card battler", "deck battler", "card game", ... ]`)
- `procedural_world` (`["procedural world", "procedural landscape", ...]`)

**Findings:**
1. There was no preset entry or keywords for classic board games like `snake and ladders`, `snakes and ladders`, `ludo`, `chutes and ladders`, `chess`, or `checkers`.
2. As a consequence, `"make a snake and ladders game"` completely bypassed deterministic preset matching and fell through to the LLM model path.

### 2.2 System Prompt Ambiguity in LLM Draft Generation
In `src/gameforge_ide/design/prompt_to_gds.py`, the `DRAFT_SYSTEM_PROMPT` provided only:
```text
You turn a game idea into a JSON object that matches the given schema exactly.
Rules:
- Choose the closest genre and camera. Prefer simple, playable designs a small team could build in a day.
...
```
**Findings:**
1. The available `Genre` enum in `src/gameforge_ide/design/gds.py` defines:
   `GRID_BOARD`, `PLATFORMER`, `ARENA_COMBAT`, `CARD_BATTLER`, `EXPLORATION`, `ACTION_ADVENTURE`, `TOP_DOWN_SHOOTER`, `DUNGEON_CRAWLER`, `PUZZLE`, `CUSTOM`.
2. The model prompt failed to enumerate the valid genres or explain that turn-based board games (like Snake and Ladders) must use `GRID_BOARD` with `FIXED_BOARD` camera.
3. Without explicit domain knowledge, local 9B/4B models associated the word `"snake"` or `"ladders"` (vertical traversal) with jumping / obstacle traversal, errantly selecting `PLATFORMER`.

### 2.3 Hardcoded Single-Player Expansion
In `src/gameforge_ide/design/expand.py`, `expand_draft()` deterministically builds the full `GameDesignSpec` from `DesignDraft`. Line 475 explicitly specified:
```python
overview = Overview(
    genre=draft.genre,
    pitch=draft.pitch,
    camera=draft.camera,
    players=1,  # <-- BUG: Hardcoded to 1 player regardless of genre or board properties!
    session_minutes=10,
)
```
**Findings:**
Board games inherently require 2 or more players (hotseat or vs AI). Hardcoding `players=1` violated board game requirements and produced single-player configurations.

### 2.4 Fallback Layout Misrouting in Master Composer
In `src/gameforge_ide/composer/compose.py` (lines 92-93):
```python
elif genre_val in ("board", "card"):
    layout_name = "board"
```
**Findings:**
`Genre` enum values are `Genre.GRID_BOARD.value == "grid_board"` and `Genre.CARD_BATTLER.value == "card_battler"`. Checking `"board"` and `"card"` evaluated to `False` for valid GDS specs, causing board games to fall through to `layout_name = "arena"`, spawning combat arenas and mannequins rather than a board.

---

## 3. Implemented Architectural Corrections

1. **Preset Catalog Expansion (`presets.py`):**
   - Implemented `preset_snake_and_ladders()` generating a verified 100-cell grid board (10x10) with 8 snake penalty transitions, 8 ladder bonus transitions, 6-sided dice rolling mechanics, and 2 player tokens.
   - Registered comprehensive board game keywords: `snake and ladders`, `snakes and ladders`, `snake & ladders`, `snakes & ladders`, `chutes and ladders`, `ludo`, `dice board game`, `roll and move`.

2. **Domain-Explicit LLM System Prompt (`prompt_to_gds.py`):**
   - Updated `DRAFT_SYSTEM_PROMPT` with clear genre definitions and mandatory rules:
     - Board games (dice, grid tiles, turn-based, tokens) MUST select `grid_board` and `fixed_board`.
     - 3D obstacle courses with jumping MUST select `platformer` and `third_person`.
     - First-person shooting MUST select `custom` / tactical FPS and `first_person`.

3. **Dynamic Player Count Extraction (`expand.py`):**
   - Configured `expand_draft()` to extract player counts dynamically from board props or entity definitions, defaulting to 2 players for `GRID_BOARD` and `CARD_BATTLER`.

4. **Corrected Composer Genre-to-Layout Routing (`compose.py`):**
   - Mapped `grid_board` and `puzzle` to `board` layout.
   - Mapped `card_battler` to `lanes` layout.

---

## 4. Verification and Semantic Validation

- Added `semantic_validate_gds()` to verify that prompt semantics (board games, combat, platforming) strictly align with the generated GDS genre and entities before pipeline execution proceeds.
