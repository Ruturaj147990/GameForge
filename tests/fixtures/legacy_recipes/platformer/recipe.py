"""Recipe: platformer (3D platformer with CharacterMovement, jumping, collectibles, checkpoints, goal, HUD).

A parameterised, verified Unreal Engine C++ game module providing:
  * AGFPlatformerCharacter   ACharacter with SpringArm, Camera, CharacterMovementComponent,
                             jump physics, grounded checks, checkpoint respawning, KillZ detection.
  * AGFPlatformerCollectible Floating/rotating collectible actor with overlap trigger and count increment.
  * AGFPlatformerCheckpoint  Mid-level checkpoint actor updating respawn location on overlap.
  * AGFPlatformerGoal        End-of-level goal actor triggering victory state when target met.
  * AGFPlatformerHUD         Canvas HUD displaying title, coins collected/target, checkpoint state,
                             victory banner, and controls legend.
  * AGFPlatformerGameMode    GameMode managing game rules, delegates, reset, and -GFSelfTest runner.
  * Automation tests         GameForge.<Game>.* (Movement, Collectibles, Checkpoint, FallRespawn, Completion, Reset).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict

from .templates import render_sources

RECIPE_ID = "platformer"
RECIPE_VERSION = "1.0.0"
SELFTEST_LOG_PASS = "GF_PLATFORMER_SELFTEST PASS"
TEST_FILTER_TEMPLATE = "GameForge.{name}"


@dataclass
class PlatformerParams:
    project_name: str = "Platformer"
    display_title: str = "3D Platformer"
    collectible_target: int = 5
    difficulty: str = "normal"          # "easy" | "normal" | "hard"
    starting_level: str = "Level1"
    player_speed: float = 600.0
    jump_velocity: float = 650.0
    gravity_scale: float = 1.2
    air_control: float = 0.35
    kill_z: float = -500.0

    def validate(self) -> None:
        if not re.match(r"^[A-Z][A-Za-z0-9]{1,30}$", self.project_name):
            raise ValueError(f"project_name must be PascalCase alphanumeric (got {self.project_name!r})")
        if not 1 <= self.collectible_target <= 50:
            raise ValueError(f"collectible_target must be between 1 and 50 (got {self.collectible_target})")
        if self.difficulty not in ("easy", "normal", "hard"):
            raise ValueError(f"difficulty must be easy|normal|hard (got {self.difficulty!r})")
        if len(self.display_title) > 60 or any(c in self.display_title for c in '"\\\n'):
            raise ValueError("display_title must be <= 60 chars without quotes, backslashes or newlines")
        if not 100.0 <= self.player_speed <= 2000.0:
            raise ValueError(f"player_speed must be between 100 and 2000 cm/s (got {self.player_speed})")
        if not 200.0 <= self.jump_velocity <= 1500.0:
            raise ValueError(f"jump_velocity must be between 200 and 1500 cm/s (got {self.jump_velocity})")
        if not 0.1 <= self.gravity_scale <= 5.0:
            raise ValueError(f"gravity_scale must be between 0.1 and 5.0 (got {self.gravity_scale})")
        if not 0.0 <= self.air_control <= 1.0:
            raise ValueError(f"air_control must be between 0.0 and 1.0 (got {self.air_control})")

    def to_dict(self) -> Dict:
        return asdict(self)


def generate(params: PlatformerParams) -> Dict[str, str]:
    """Return {relative_path: content} for the game module sources."""
    params.validate()
    return render_sources(params)
