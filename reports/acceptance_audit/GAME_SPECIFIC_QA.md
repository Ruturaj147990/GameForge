# GameForge — Game-Specific QA & False PASS Elimination Audit

**Audit Date:** 2026-11-03T14:20:00Z  
**Investigator:** Antigravity Autonomous Inspector & Remediation Agent  
**Status:** COMPLETE & VERIFIED  

---

## 1. Executive Summary

This audit addresses the false confidence created by generic automation tests in earlier GameForge builds. During the Snake and Ladders build, the automation test filter ran:
```text
Automation RunTests GameForge.Kit;Quit
```
which executed only three generic schema unit tests:
- `CountAtLeast` (checks if an event count comparison works)
- `NestingAndDepth` (checks if nested rule conditions evaluate)
- `StatOperators` (checks if $>, <, \ge, \le$ operator math works)

All 3 tests passed with green checkmarks. However, none of these tests verified that Snake and Ladders was playable, that a board existed, that dice rolled, that snakes penalised players, or that winning was achievable.

---

## 2. Root Cause of False PASS Results

1. **Hardcoded Test Filter:**
   In `legacy_stages.py::legacy_tests` and `composer/plan.py`, the default test filter was set to `"GameForge.Kit"`.
2. **Decoupled Scenario Harness:**
   The deterministic scenario QA harness (`src/gameforge_ide/qa/runner.py`) tested kit baseline scenarios (`collect_3`, `quest_complete`) rather than deriving game-specific scenarios dynamically from the project's `GameDesignSpec`.
3. **Headless Execution Limitations:**
   Unreal Engine commandlet tests run with `CanEverRender() == false`. While useful for unit logic, they cannot detect missing visual elements, broken HUD widgets, or camera occlusion.

---

## 3. Game-Specific Acceptance Test Specification

GameForge now dynamically derives game-specific acceptance tests from the GDS goals, rules, and entities (`src/gameforge_ide/qa/game_spec_tests.py`):

### 3.1 Board Game Acceptance Matrix (e.g. Snake and Ladders)

| Test ID | Requirement | Test Assertion | Pass Criteria |
|---|---|---|---|
| **SNAKE_01** | Board Structure | Query `AGameForgeGridBoard` cell count | Exactly 100 active cells ($10 \times 10$) |
| **SNAKE_02** | Cell Numbering | Query cell coordinates | Linear sequence $1 \to 100$ alternating row directions |
| **SNAKE_03** | Dice Mechanics | Roll RNG generator 100 times | All outcomes $\in [1, 6]$, mean $\approx 3.5$ |
| **SNAKE_04** | Token Movement | Simulate roll $D=4$ from cell 1 | Player token moves to cell 5 |
| **SNAKE_05** | Snake Transition | Token lands on snake head (e.g. cell 16) | Token teleports to snake tail (e.g. cell 6) |
| **SNAKE_06** | Ladder Transition | Token lands on ladder bottom (e.g. cell 4) | Token teleports to ladder top (e.g. cell 14) |
| **SNAKE_07** | Turn Alternation | Player 1 completes roll and move | Active player flips to Player 2 |
| **SNAKE_08** | Overshoot Rule | Player at cell 98 rolls 4 | Player bounces to cell 98 (does not win) |
| **SNAKE_09** | Win Condition | Player lands exactly on cell 100 | Event `game.won` fires, input locked |
| **SNAKE_10** | Restart | Press `IA_Restart` / `R` | Tokens reset to cell 0, turn resets to Player 1 |

### 3.2 Platformer Acceptance Matrix

| Test ID | Requirement | Test Assertion | Pass Criteria |
|---|---|---|---|
| **PLAT_01** | Locomotion | Inject `IA_Move` | Character velocity magnitude $> 500$ cm/s |
| **PLAT_02** | Jump Physics | Inject `IA_Jump` | Character Z-velocity $> 600$, `IsFalling() == true` |
| **PLAT_03** | Collectibles | Check level actors | Collectible count matches GDS target (e.g. 5) |
| **PLAT_04** | Goal Trigger | Character enters goal volume | Event `goal.reached` emitted |
| **PLAT_05** | Win Condition | Collect all + enter goal | Event `game.won` emitted |

### 3.3 Tactical FPS / Arena Combat Acceptance Matrix

| Test ID | Requirement | Test Assertion | Pass Criteria |
|---|---|---|---|
| **FPS_01** | First-Person View | Check Camera Component | Boom target arm length == 0.0, attached to mesh head socket |
| **FPS_02** | Weapon Viewmodel | Check Weapon Mesh | Attached to camera socket, visible in viewport |
| **FPS_03** | Projectile Fire | Inject `IA_Fire` | Projectile actor spawned with orange tracer material |
| **FPS_04** | Combat Damage | Projectile collides with enemy bot | Bot health decreased by weapon damage |
| **FPS_05** | Defeat All | All enemy bots eliminated | Event `wave.cleared` or `game.won` emitted |

---

## 4. Pipeline Stage Verification Gates

No pipeline stage is permitted to return `StepOutcome(True)` based solely on function return:

1. **Design Stage:** Validated against `semantic_validate_gds()` to guarantee prompt keywords align with the GDS genre.
2. **Scaffold Stage:** Validates that `<Project>.Build.cs`, `.uproject`, and target rules exist and match the project name.
3. **Build Stage:** Parses UBT compilation logs to ensure generated classes were compiled into the target binary.
4. **Assemble Stage:** Performs Unreal Editor read-back of placed actors (`actors_in_level`), verifying actor classes and coordinates match the LevelPlan.
5. **Scenario Stage:** Runs game-specific scenarios and asserts that expected gameplay events (`game.won`, `pickup.collected`) are logged.
6. **Package Stage:** Verifies `<Project>.exe` container exists on disk with non-zero size before marking stage DONE.
