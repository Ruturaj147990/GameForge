"""Recipe: arena_combat (Top-down / 3D arena combat with player attack, AI navigation, waves, and HUD).

A parameterised, verified Unreal Engine 5.7 C++ game module providing:
  * AGFArenaCharacter      ACharacter with SpringArm, Camera, CharacterMovementComponent,
                           hitscan/sphere attack, health management, damage interface.
  * AGFArenaEnemy          ACharacter AI enemy with PawnSensing/Awareness, melee attack,
                           health, damage reception, death delegate, and score attribution.
  * AGFArenaAIController   AAIController with real navigation-based pursuit (MoveToActor / MoveToLocation).
  * AGFArenaHUD            AHUD rendering player health bar, wave number, enemies remaining, score,
                           game status (READY, IN_PROGRESS, VICTORY, DEFEAT), and controls legend.
  * AGFArenaGameMode       AGameModeBase managing match lifecycle, wave spawning, enemy tracking,
                           victory/defeat predicates, reset, and -GFSelfTest runner.
  * Automation tests       GameForge.<Game>.* (CombatDamage, HealthBounds, WaveProgression, AIController, Reset).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict

from .templates import render_sources

RECIPE_ID = "arena_combat"
RECIPE_VERSION = "1.0.0"
SELFTEST_LOG_PASS = "GF_ARENA_SELFTEST PASS"
TEST_FILTER_TEMPLATE = "GameForge.{name}"


@dataclass
class ArenaCombatParams:
    project_name: str = "ArenaCombat"
    display_title: str = "Arena Combat"
    difficulty: str = "normal"          # "easy" | "normal" | "hard"
    starting_level: str = "Level1"
    wave_count: int = 3
    enemies_per_wave: int = 4
    player_max_health: float = 100.0
    player_attack_damage: float = 35.0
    player_attack_range: float = 250.0
    player_attack_cooldown: float = 0.4
    enemy_max_health: float = 50.0
    enemy_attack_damage: float = 15.0
    enemy_attack_range: float = 120.0
    enemy_attack_cooldown: float = 1.0
    enemy_speed: float = 350.0

    def validate(self) -> None:
        if not re.match(r"^[A-Z][A-Za-z0-9]{1,30}$", self.project_name):
            raise ValueError(f"project_name must be PascalCase alphanumeric (got {self.project_name!r})")
        if not 1 <= self.wave_count <= 20:
            raise ValueError(f"wave_count must be between 1 and 20 (got {self.wave_count})")
        if not 1 <= self.enemies_per_wave <= 50:
            raise ValueError(f"enemies_per_wave must be between 1 and 50 (got {self.enemies_per_wave})")
        if self.difficulty not in ("easy", "normal", "hard"):
            raise ValueError(f"difficulty must be easy|normal|hard (got {self.difficulty!r})")
        if len(self.display_title) > 60 or any(c in self.display_title for c in '"\\\n'):
            raise ValueError("display_title must be <= 60 chars without quotes, backslashes or newlines")
        if not 10.0 <= self.player_max_health <= 1000.0:
            raise ValueError(f"player_max_health must be between 10 and 1000 (got {self.player_max_health})")
        if not 5.0 <= self.player_attack_damage <= 500.0:
            raise ValueError(f"player_attack_damage must be between 5 and 500 (got {self.player_attack_damage})")
        if not 50.0 <= self.player_attack_range <= 1000.0:
            raise ValueError(f"player_attack_range must be between 50 and 1000 cm (got {self.player_attack_range})")
        if not 0.05 <= self.player_attack_cooldown <= 5.0:
            raise ValueError(f"player_attack_cooldown must be between 0.05 and 5.0 s (got {self.player_attack_cooldown})")
        if not 5.0 <= self.enemy_max_health <= 1000.0:
            raise ValueError(f"enemy_max_health must be between 5 and 1000 (got {self.enemy_max_health})")
        if not 1.0 <= self.enemy_attack_damage <= 200.0:
            raise ValueError(f"enemy_attack_damage must be between 1 and 200 (got {self.enemy_attack_damage})")
        if not 50.0 <= self.enemy_speed <= 1200.0:
            raise ValueError(f"enemy_speed must be between 50 and 1200 cm/s (got {self.enemy_speed})")

    def to_dict(self) -> Dict:
        return asdict(self)


def generate(params: ArenaCombatParams) -> Dict[str, str]:
    """Return {relative_path: content} for the arena combat game module sources."""
    params.validate()
    return render_sources(params)
