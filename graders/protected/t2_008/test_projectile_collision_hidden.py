"""GameForge Trusted Hidden Grader Oracle for T2-008 Projectile Collision and Combat Damage.

Isolated in graders/protected/t2_008/ and NEVER exposed to candidate agents.
Injected only into isolated grading workspaces to verify projectile collision physics and combat invariants.
"""

from __future__ import annotations

import math
import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SimulatedCharacter:
    health: float = 100.0
    max_health: float = 100.0
    is_dead: bool = False
    is_damageable: bool = True
    invuln_duration: float = 0.75
    last_hit_time: float = -100.0
    death_events: int = 0


@dataclass
class SimulatedProjectile:
    speed: float = 2000.0
    damage: float = 20.0
    lifespan: float = 5.0
    owner: Optional[SimulatedCharacter] = None
    bHasImpacted: bool = False
    collision_enabled: bool = True
    is_hidden: bool = False
    is_destroyed: bool = False
    damage_applied_count: int = 0
    impact_events: List[Dict[str, Any]] = field(default_factory=list)


def process_projectile_hit(proj: SimulatedProjectile, target: Optional[SimulatedCharacter], current_time: float = 0.0) -> bool:
    """Simulates native AProjectileActor::OnHit / overlap collision logic."""
    if proj.bHasImpacted:
        return False

    if target is None or not target.is_damageable:
        proj.bHasImpacted = True
        proj.collision_enabled = False
        proj.is_hidden = True
        return False

    # Owner exclusion check
    if target is proj.owner:
        return False

    damage = proj.damage
    if not math.isfinite(damage) or damage <= 0.0:
        return False

    proj.bHasImpacted = True
    proj.collision_enabled = False
    proj.is_hidden = True

    if target.is_dead:
        return False

    # Invulnerability check
    if (current_time - target.last_hit_time) < target.invuln_duration:
        return False

    target.last_hit_time = current_time
    target.health = max(0.0, target.health - damage)
    proj.damage_applied_count += 1
    proj.impact_events.append({"time": current_time, "damage": damage, "target_health": target.health})

    if target.health <= 0.0 and not target.is_dead:
        target.is_dead = True
        target.death_events += 1

    return True


def test_hidden_proj1_valid_hit_damage():
    owner = SimulatedCharacter(health=100.0)
    target = SimulatedCharacter(health=100.0)
    proj = SimulatedProjectile(damage=20.0, owner=owner)

    hit = process_projectile_hit(proj, target, current_time=0.0)
    assert hit is True
    assert target.health == 80.0
    assert proj.damage_applied_count == 1
    assert proj.bHasImpacted is True


def test_hidden_proj2_duplicate_hit_prevention():
    owner = SimulatedCharacter(health=100.0)
    target = SimulatedCharacter(health=100.0)
    proj = SimulatedProjectile(damage=20.0, owner=owner)

    hit1 = process_projectile_hit(proj, target, current_time=0.0)
    assert hit1 is True
    assert target.health == 80.0

    hit2 = process_projectile_hit(proj, target, current_time=0.01)
    assert hit2 is False
    assert target.health == 80.0
    assert proj.damage_applied_count == 1


def test_hidden_proj3_owner_exclusion():
    owner = SimulatedCharacter(health=100.0)
    proj = SimulatedProjectile(damage=20.0, owner=owner)

    hit_owner = process_projectile_hit(proj, owner, current_time=0.0)
    assert hit_owner is False
    assert owner.health == 100.0
    assert proj.damage_applied_count == 0
    assert proj.bHasImpacted is False


def test_hidden_proj4_invalid_target_safety():
    owner = SimulatedCharacter(health=100.0)
    non_target = SimulatedCharacter(is_damageable=False)
    proj = SimulatedProjectile(damage=20.0, owner=owner)

    hit = process_projectile_hit(proj, non_target, current_time=0.0)
    assert hit is False
    assert proj.damage_applied_count == 0
    assert proj.bHasImpacted is True


def test_hidden_proj5_blocking_geometry_resolution():
    owner = SimulatedCharacter(health=100.0)
    proj = SimulatedProjectile(damage=20.0, owner=owner)

    hit = process_projectile_hit(proj, None, current_time=0.0)
    assert hit is False
    assert proj.bHasImpacted is True
    assert proj.collision_enabled is False


def test_hidden_proj6_post_impact_cleanup():
    owner = SimulatedCharacter(health=100.0)
    target = SimulatedCharacter(health=100.0)
    proj = SimulatedProjectile(damage=20.0, owner=owner)

    process_projectile_hit(proj, target, current_time=0.0)
    assert proj.bHasImpacted is True
    assert proj.collision_enabled is False
    assert proj.is_hidden is True


def test_hidden_proj7_lifetime_cleanup():
    proj = SimulatedProjectile(lifespan=5.0)
    assert proj.lifespan == 5.0
    assert proj.bHasImpacted is False


def test_hidden_proj8_invulnerability_respected():
    owner = SimulatedCharacter(health=100.0)
    target = SimulatedCharacter(health=100.0)
    p1 = SimulatedProjectile(damage=20.0, owner=owner)
    process_projectile_hit(p1, target, current_time=0.0)
    assert target.health == 80.0

    # Within 0.75s invulnerability window
    p2 = SimulatedProjectile(damage=20.0, owner=owner)
    hit_during_invuln = process_projectile_hit(p2, target, current_time=0.40)
    assert hit_during_invuln is False
    assert target.health == 80.0


def test_hidden_proj9_post_expiry_hit():
    owner = SimulatedCharacter(health=100.0)
    target = SimulatedCharacter(health=100.0)
    p1 = SimulatedProjectile(damage=20.0, owner=owner)
    process_projectile_hit(p1, target, current_time=0.0)
    assert target.health == 80.0

    # After 0.75s invulnerability window
    p2 = SimulatedProjectile(damage=20.0, owner=owner)
    hit_after = process_projectile_hit(p2, target, current_time=0.80)
    assert hit_after is True
    assert target.health == 60.0


def test_hidden_proj10_invalid_config_safety():
    owner = SimulatedCharacter(health=100.0)
    target = SimulatedCharacter(health=100.0)

    p_neg = SimulatedProjectile(damage=-20.0, owner=owner)
    assert process_projectile_hit(p_neg, target, current_time=0.0) is False
    assert target.health == 100.0

    p_nan = SimulatedProjectile(damage=float("nan"), owner=owner)
    assert process_projectile_hit(p_nan, target, current_time=0.0) is False
    assert target.health == 100.0


def test_hidden_proj11_death_and_zero_clamp():
    owner = SimulatedCharacter(health=100.0)
    mortal = SimulatedCharacter(health=10.0)
    p1 = SimulatedProjectile(damage=30.0, owner=owner)

    hit1 = process_projectile_hit(p1, mortal, current_time=0.0)
    assert hit1 is True
    assert mortal.health == 0.0
    assert mortal.is_dead is True
    assert mortal.death_events == 1

    p2 = SimulatedProjectile(damage=30.0, owner=owner)
    hit2 = process_projectile_hit(p2, mortal, current_time=1.0)
    assert hit2 is False
    assert mortal.death_events == 1


def test_hidden_proj12_cross_system_parity():
    owner = SimulatedCharacter(health=100.0)
    target = SimulatedCharacter(health=100.0)
    proj = SimulatedProjectile(damage=20.0, owner=owner)

    assert process_projectile_hit(proj, target, current_time=0.0) is True
    assert target.health == 80.0
