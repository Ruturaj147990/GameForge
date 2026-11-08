"""Recipe: card_battler (Single-player 3-lane card battler with card definitions, energy, combat, AI opponent, HUD).

A parameterised, verified Unreal Engine 5.7 C++ game module providing:
  * GFCardTypes.h          Card definitions (struct FGFCardDef, FGFCardInstance, ELaneCombatSide, EMatchState).
  * GFCardStateComponent   ActorComponent managing deck, draw pile, hand, lanes, discard pile, energy, and base health.
  * GFCardOpponentAI       AI opponent evaluating hand and legal lanes to play cards and end turn.
  * GFCardGameMode         GameMode orchestrating turn flow (PlayerTurn -> OpponentTurn -> CombatResolution -> RoundEnd),
                           lane combat resolution (lanes 0, 1, 2 sequentially; unit vs unit simultaneous damage; unblocked
                           attacks strike enemy base), victory/defeat checks, match reset, and -GFSelfTest runner.
  * GFCardHUD              Canvas HUD rendering player/opponent base health bars, current energy/max energy,
                           3 combat lanes (Opponent units vs Player units with Attack/Health), Hand cards (Name, Cost, Atk/HP),
                           turn/state banner (PLAYER_TURN, OPPONENT_TURN, VICTORY, DEFEAT), and controls legend.
  * Automation tests       GameForge.<Game>.* (CardDefs, DrawNoDuplicates, EnergyCost, LanePlayRules, CombatResolution,
                           OpponentAILegality, VictoryDefeat, MatchReset).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict

from .templates import render_sources

RECIPE_ID = "card_battler"
RECIPE_VERSION = "1.0.0"
SELFTEST_LOG_PASS = "GF_CARD_SELFTEST PASS"
TEST_FILTER_TEMPLATE = "GameForge.{name}"


@dataclass
class CardBattlerParams:
    project_name: str = "CardBattler"
    display_title: str = "Card Battler"
    difficulty: str = "normal"          # "easy" | "normal" | "hard"
    starting_level: str = "Level1"
    player_base_health: int = 30
    opponent_base_health: int = 30
    starting_hand_size: int = 4
    max_hand_size: int = 7
    base_energy_per_turn: int = 3
    lane_count: int = 3

    def validate(self) -> None:
        if not re.match(r"^[A-Z][A-Za-z0-9]{1,30}$", self.project_name):
            raise ValueError(f"project_name must be PascalCase alphanumeric (got {self.project_name!r})")
        if not 5 <= self.player_base_health <= 200:
            raise ValueError(f"player_base_health must be between 5 and 200 (got {self.player_base_health})")
        if not 5 <= self.opponent_base_health <= 200:
            raise ValueError(f"opponent_base_health must be between 5 and 200 (got {self.opponent_base_health})")
        if not 1 <= self.starting_hand_size <= 10:
            raise ValueError(f"starting_hand_size must be between 1 and 10 (got {self.starting_hand_size})")
        if not 1 <= self.base_energy_per_turn <= 10:
            raise ValueError(f"base_energy_per_turn must be between 1 and 10 (got {self.base_energy_per_turn})")
        if self.lane_count != 3:
            raise ValueError(f"lane_count must be 3 (got {self.lane_count})")
        if self.difficulty not in ("easy", "normal", "hard"):
            raise ValueError(f"difficulty must be easy|normal|hard (got {self.difficulty!r})")
        if len(self.display_title) > 60 or any(c in self.display_title for c in '"\\\n'):
            raise ValueError("display_title must be <= 60 chars without quotes, backslashes or newlines")

    def to_dict(self) -> Dict:
        return asdict(self)


def generate(params: CardBattlerParams) -> Dict[str, str]:
    """Return {relative_path: content} for the card battler game module sources."""
    params.validate()
    return render_sources(params)
