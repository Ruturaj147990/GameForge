"""Recipe: procedural_world (Procedural landscape, spline road, vegetation scatter, landmark, and traversal).

A parameterised, verified Unreal Engine C++ game module providing:
  * AGFProceduralCharacter  ACharacter with SpringArm, Camera, CharacterMovementComponent,
                            road waypoint tracking, and landmark discovery interaction.
  * AGFProceduralLandmark   Landmark POI actor with collision geometry and overlap trigger box.
  * AGFProceduralHUD        Canvas & UMG HUD displaying landscape stats, biome, traversal distance,
                            and discovery banners.
  * AGFProceduralGameMode   GameMode managing world lifecycle, discovery delegates, reset, and -GFSelfTest.
  * Automation tests        GameForge.<Game>.* (WorldConfig, RoadSpline, FoliageDensity, LandmarkTrigger, TraversalAndReset).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict

from .templates import render_sources

RECIPE_ID = "procedural_world"
RECIPE_VERSION = "1.0.0"
SELFTEST_LOG_PASS = "GF_PROCEDURAL_SELFTEST PASS"
TEST_FILTER_TEMPLATE = "GameForge.{name}"


@dataclass
class ProceduralWorldParams:
    project_name: str = "ProceduralWorld"
    display_title: str = "Procedural Landscape"
    seed: int = 2026
    terrain_type: str = "Valley"        # "Valley" | "Mountains" | "Plateau" | "Hills"
    elevation_scale: float = 1800.0     # Maximum vertical relief in cm
    component_count_x: int = 2          # Landscape components along X
    component_count_y: int = 2          # Landscape components along Y
    quads_per_section: int = 63         # 63 quads per section standard
    sections_per_component: int = 1     # 1 section per component
    road_width: float = 350.0           # Road width in cm
    foliage_density: int = 40           # Target foliage instance count
    landmark_type: str = "Ruins"        # "Ruins" | "Tower" | "Shrine"
    player_speed: float = 650.0         # Traversal walk speed in cm/s
    starting_level: str = "Level1"

    def validate(self) -> None:
        if not re.match(r"^[A-Z][A-Za-z0-9]{1,30}$", self.project_name):
            raise ValueError(f"project_name must be PascalCase alphanumeric (got {self.project_name!r})")
        if self.terrain_type not in ("Valley", "Mountains", "Plateau", "Hills"):
            raise ValueError(f"terrain_type must be Valley|Mountains|Plateau|Hills (got {self.terrain_type!r})")
        if not 100.0 <= self.elevation_scale <= 20000.0:
            raise ValueError(f"elevation_scale must be between 100 and 20000 cm (got {self.elevation_scale})")
        if not 1 <= self.component_count_x <= 16:
            raise ValueError(f"component_count_x must be between 1 and 16 (got {self.component_count_x})")
        if not 1 <= self.component_count_y <= 16:
            raise ValueError(f"component_count_y must be between 1 and 16 (got {self.component_count_y})")
        if not 50.0 <= self.road_width <= 2000.0:
            raise ValueError(f"road_width must be between 50 and 2000 cm (got {self.road_width})")
        if not 0 <= self.foliage_density <= 1000:
            raise ValueError(f"foliage_density must be between 0 and 1000 (got {self.foliage_density})")
        if self.landmark_type not in ("Ruins", "Tower", "Shrine"):
            raise ValueError(f"landmark_type must be Ruins|Tower|Shrine (got {self.landmark_type!r})")
        if not 100.0 <= self.player_speed <= 2500.0:
            raise ValueError(f"player_speed must be between 100 and 2500 cm/s (got {self.player_speed})")
        if len(self.display_title) > 60 or any(c in self.display_title for c in '"\\\n'):
            raise ValueError("display_title must be <= 60 chars without quotes, backslashes or newlines")

    def to_dict(self) -> Dict:
        return asdict(self)


def generate(params: ProceduralWorldParams) -> Dict[str, str]:
    """Return {relative_path: content} for the game module sources."""
    params.validate()
    return render_sources(params)
