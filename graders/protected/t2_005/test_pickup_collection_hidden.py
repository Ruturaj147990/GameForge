"""GameForge Trusted Hidden Grader Oracle for T2-005 Pickup Collection System.

Isolated in graders/protected/t2_005/ and NEVER exposed to candidate agents.
Injected only into isolated grading workspaces to verify collection invariants.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CharacterState:
    health: float = 100.0
    max_health: float = 100.0
    stamina: float = 100.0
    max_stamina: float = 100.0
    is_dead: bool = False
    is_valid_target: bool = True


@dataclass
class PickupSim:
    pickup_type: str = "Health"
    amount: float = 25.0
    bIsConsumed: bool = False
    bPickupAvailable: bool = True
    bIsProcessing: bool = False
    collision_enabled: bool = True
    is_hidden: bool = False
    events: List[Dict[str, Any]] = field(default_factory=list)

    # Defect flags for grading evaluation
    defect_duplicate: bool = False
    defect_full_resource: bool = False
    defect_wrong_target: bool = False

    def attempt_collect(self, target: CharacterState) -> bool:
        if not self.defect_duplicate:
            if not self.bPickupAvailable or self.bIsConsumed or self.bIsProcessing:
                return False
        else:
            if self.bIsProcessing:
                return False

        if not target or not target.is_valid_target:
            return False

        if not math.isfinite(self.amount) or self.amount <= 0.0:
            return False

        self.bIsProcessing = True
        effect_applied = False
        target_res = self.pickup_type

        if self.defect_wrong_target:
            target_res = "Stamina" if target_res == "Health" else "Health"

        if target_res == "Health":
            if not target.is_dead and target.health < target.max_health:
                new_h = min(target.max_health, target.health + self.amount)
                if new_h > target.health:
                    target.health = new_h
                    effect_applied = True
        elif target_res == "Stamina":
            if target.stamina < target.max_stamina:
                new_s = min(target.max_stamina, target.stamina + self.amount)
                if new_s > target.stamina:
                    target.stamina = new_s
                    effect_applied = True

        if self.defect_full_resource:
            effect_applied = True

        if effect_applied:
            self.bIsConsumed = True
            self.bPickupAvailable = False
            self.bIsProcessing = False
            self.collision_enabled = False
            self.is_hidden = True
            self.events.append({
                "type": self.pickup_type,
                "amount": self.amount,
                "health": target.health,
                "stamina": target.stamina,
            })
            return True

        self.bIsProcessing = False
        return False


def test_hidden_p1_valid_health_collection():
    pickup = PickupSim(pickup_type="Health", amount=25.0)
    char = CharacterState(health=50.0, max_health=100.0)
    assert pickup.attempt_collect(char) is True
    assert char.health == 75.0
    assert len(pickup.events) == 1
    assert pickup.bIsConsumed is True
    assert pickup.bPickupAvailable is False


def test_hidden_p2_repeated_overlap_prevention():
    pickup = PickupSim(pickup_type="Health", amount=25.0)
    char = CharacterState(health=50.0, max_health=100.0)
    assert pickup.attempt_collect(char) is True
    # Immediate second overlap notification
    assert pickup.attempt_collect(char) is False
    assert char.health == 75.0
    assert len(pickup.events) == 1


def test_hidden_p3_reentry_after_consumed():
    pickup = PickupSim(pickup_type="Health", amount=25.0)
    char = CharacterState(health=50.0, max_health=100.0)
    assert pickup.attempt_collect(char) is True
    # Character re-enters pickup location
    assert pickup.attempt_collect(char) is False
    assert len(pickup.events) == 1


def test_hidden_p4_full_health_rejection():
    pickup = PickupSim(pickup_type="Health", amount=25.0)
    char = CharacterState(health=100.0, max_health=100.0)
    assert pickup.attempt_collect(char) is False
    assert char.health == 100.0
    assert pickup.bIsConsumed is False
    assert pickup.bPickupAvailable is True
    assert len(pickup.events) == 0


def test_hidden_p5_valid_stamina_collection():
    pickup = PickupSim(pickup_type="Stamina", amount=20.0)
    char = CharacterState(stamina=40.0, max_stamina=100.0)
    assert pickup.attempt_collect(char) is True
    assert char.stamina == 60.0
    assert len(pickup.events) == 1
    assert pickup.bIsConsumed is True


def test_hidden_p6_resource_clamping():
    pickup = PickupSim(pickup_type="Health", amount=25.0)
    char = CharacterState(health=90.0, max_health=100.0)
    assert pickup.attempt_collect(char) is True
    assert char.health == 100.0
    assert len(pickup.events) == 1


def test_hidden_p7_invalid_target_rejection():
    pickup = PickupSim(pickup_type="Health", amount=25.0)
    invalid_char = CharacterState(is_valid_target=False)
    assert pickup.attempt_collect(invalid_char) is False
    assert pickup.bIsConsumed is False
    assert len(pickup.events) == 0


def test_hidden_p8_dead_player_rejection():
    pickup = PickupSim(pickup_type="Health", amount=25.0)
    dead_char = CharacterState(health=0.0, is_dead=True)
    assert pickup.attempt_collect(dead_char) is False
    assert dead_char.health == 0.0
    assert dead_char.is_dead is True
    assert pickup.bIsConsumed is False
    assert len(pickup.events) == 0


def test_hidden_p9_invalid_amount_rejection():
    pickup_neg = PickupSim(pickup_type="Health", amount=-10.0)
    char = CharacterState(health=50.0)
    assert pickup_neg.attempt_collect(char) is False
    assert char.health == 50.0

    pickup_nan = PickupSim(pickup_type="Health", amount=float("nan"))
    assert pickup_nan.attempt_collect(char) is False


def test_hidden_p10_collection_race_resolution():
    pickup = PickupSim(pickup_type="Health", amount=25.0)
    char_a = CharacterState(health=50.0)
    char_b = CharacterState(health=50.0)
    res_a = pickup.attempt_collect(char_a)
    res_b = pickup.attempt_collect(char_b)
    assert (res_a and not res_b) or (res_b and not res_a)
    assert len(pickup.events) == 1


def test_hidden_p11_reentrancy_protection():
    pickup = PickupSim(pickup_type="Health", amount=25.0)
    pickup.bIsProcessing = True
    char = CharacterState(health=50.0)
    assert pickup.attempt_collect(char) is False
    assert len(pickup.events) == 0


def test_hidden_p12_collision_and_visibility_shutdown():
    pickup = PickupSim(pickup_type="Health", amount=25.0)
    char = CharacterState(health=50.0)
    assert pickup.attempt_collect(char) is True
    assert pickup.collision_enabled is False
    assert pickup.is_hidden is True
    assert pickup.bIsConsumed is True
