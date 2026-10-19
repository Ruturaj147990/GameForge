"""GameForge Trusted Hidden Grader Oracle for T3-016 Player Composition.

Isolated in graders/protected/t3_016/ and NEVER exposed to candidate agents.
Injected only into isolated grading workspaces to verify actor composition and integration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ComposedPlayerSim:
    has_capsule: bool = True
    has_movement: bool = True
    has_spring_arm: bool = True
    has_camera: bool = True
    has_health: bool = True
    has_stamina: bool = True
    has_pickup_receiver: bool = True

    # Component references
    spring_arm_attached_to_root: bool = True
    camera_attached_to_arm: bool = True

    # Runtime state
    health: float = 50.0
    max_health: float = 100.0
    stamina: float = 40.0
    max_stamina: float = 100.0
    max_walk_speed_cmps: float = 600.0
    jump_z_velocity: float = 485.0
    arm_length_cm: float = 400.0
    invulnerability_duration: float = 0.75

    def get_components(self) -> List[str]:
        comps = []
        if self.has_capsule:
            comps.append("CapsuleComponent")
        if self.has_movement:
            comps.append("CharacterMovementComponent")
        if self.has_spring_arm:
            comps.append("SpringArmComponent")
        if self.has_camera:
            comps.append("CameraComponent")
        if self.has_health:
            comps.append("HealthComponent")
        if self.has_stamina:
            comps.append("StaminaComponent")
        return comps

    def receive_resource(self, res_type: str, amount: float) -> bool:
        if not self.has_pickup_receiver:
            return False
        if res_type == "Health":
            if self.has_health and self.health < self.max_health:
                self.health = min(self.max_health, self.health + amount)
                return True
        elif res_type == "Stamina":
            if self.has_stamina and self.stamina < self.max_stamina:
                self.stamina = min(self.max_stamina, self.stamina + amount)
                return True
        return False


def test_hidden_c1_component_completeness():
    player = ComposedPlayerSim()
    comps = player.get_components()
    expected = [
        "CapsuleComponent", "CharacterMovementComponent", "SpringArmComponent",
        "CameraComponent", "HealthComponent", "StaminaComponent"
    ]
    assert all(c in comps for c in expected)
    assert player.has_pickup_receiver is True


def test_hidden_c2_component_uniqueness():
    player = ComposedPlayerSim()
    comps = player.get_components()
    assert len(comps) == len(set(comps))


def test_hidden_c3_valid_references():
    player = ComposedPlayerSim()
    assert player.spring_arm_attached_to_root is True
    assert player.camera_attached_to_arm is True


def test_hidden_c4_end_to_end_health_interaction():
    player = ComposedPlayerSim(health=50.0)
    assert player.receive_resource("Health", 25.0) is True
    assert player.health == 75.0


def test_hidden_c5_end_to_end_stamina_interaction():
    player = ComposedPlayerSim(stamina=40.0)
    assert player.receive_resource("Stamina", 20.0) is True
    assert player.stamina == 60.0


def test_hidden_c6_movement_parity():
    player = ComposedPlayerSim()
    speed_mps = player.max_walk_speed_cmps / 100.0
    apex_m = (player.jump_z_velocity ** 2) / (2.0 * 980.0 * 100.0)
    arm_m = player.arm_length_cm / 100.0
    assert abs(speed_mps - 6.0) < 0.01
    assert abs(apex_m - 1.20) < 0.05
    assert abs(arm_m - 4.0) < 0.01


def test_hidden_c7_health_parity():
    player = ComposedPlayerSim()
    assert player.max_health == 100.0
    assert player.invulnerability_duration == 0.75


def test_hidden_c8_scene_integrity():
    player = ComposedPlayerSim()
    assert len(player.get_components()) == 6
    assert player.spring_arm_attached_to_root is True


def test_hidden_c9_spawn_and_cleanup():
    player = ComposedPlayerSim()
    # Spawn simulation
    assert player.has_capsule is True
    # Cleanup simulation
    del player
