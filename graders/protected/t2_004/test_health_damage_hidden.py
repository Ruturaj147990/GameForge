"""GameForge Trusted Hidden Grader Oracle for T2-004 Health and Damage System.

This file is isolated in graders/protected/ and is NEVER exposed to candidate agents.
It executes inside the isolated grading workspace and verifies all temporal and event invariants.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class HealthComponentSim:
    """Deterministic simulation of the health component specification."""
    max_health: float = 100.0
    current_health: float = 100.0
    is_dead: bool = False
    invulnerability_duration: float = 0.75
    last_accepted_hit_time: float = -1000.0
    current_time: float = 0.0

    # Event tracking
    health_changed_events: List[Dict[str, float]] = field(default_factory=list)
    damage_accepted_events: List[Dict[str, float]] = field(default_factory=list)
    death_events: int = 0
    event_order: List[str] = field(default_factory=list)
    is_processing: bool = False

    def advance_time(self, delta_seconds: float):
        if math.isfinite(delta_seconds) and delta_seconds >= 0.0:
            self.current_time += delta_seconds

    def is_invulnerable(self) -> bool:
        if self.is_dead:
            return false
        return (self.current_time - self.last_accepted_hit_time) < self.invulnerability_duration

    def apply_damage(self, damage_amount: float) -> bool:
        if self.is_processing:
            return False
        if not math.isfinite(damage_amount) or damage_amount <= 0.0:
            return False
        if self.is_dead:
            return False
        if (self.current_time - self.last_accepted_hit_time) < self.invulnerability_duration:
            return False

        self.is_processing = True
        self.last_accepted_hit_time = self.current_time

        old_health = self.current_health
        new_health = max(0.0, min(self.max_health, old_health - damage_amount))
        delta = new_health - old_health
        self.current_health = new_health

        # Event: Health Changed
        self.health_changed_events.append({"new_health": new_health, "delta": delta, "time": self.current_time})
        self.event_order.append("OnHealthChanged")

        # Event: Damage Accepted
        self.damage_accepted_events.append({"damage": damage_amount, "remaining": new_health, "time": self.current_time})
        self.event_order.append("OnDamageAccepted")

        # Event: Death
        if self.current_health <= 0.0 and not self.is_dead:
            self.is_dead = True
            self.death_events += 1
            self.event_order.append("OnDeath")

        self.is_processing = False
        return True

    def apply_healing(self, heal_amount: float) -> bool:
        if self.is_processing:
            return False
        if not math.isfinite(heal_amount) or heal_amount <= 0.0:
            return False
        if self.is_dead:
            return False
        if self.current_health >= self.max_health:
            return False

        self.is_processing = True
        old_health = self.current_health
        new_health = min(self.max_health, old_health + heal_amount)
        delta = new_health - old_health

        if delta > 0.0:
            self.current_health = new_health
            self.health_changed_events.append({"new_health": new_health, "delta": delta, "time": self.current_time})
            self.event_order.append("OnHealthChanged")
            self.is_processing = False
            return True

        self.is_processing = False
        return False


def run_all_hidden_probes(candidate_eval_fn=None) -> Dict[str, Any]:
    """Runs the complete suite of 16 hidden acceptance probes."""
    probe_results = {}

    # Probe 1: Initial state
    sim = candidate_eval_fn() if candidate_eval_fn else HealthComponentSim()
    p1_pass = (
        sim.current_health == 100.0
        and not sim.is_dead
        and len(sim.health_changed_events) == 0
        and len(sim.damage_accepted_events) == 0
        and sim.death_events == 0
    )
    probe_results["probe_initial_state"] = {
        "passed": p1_pass,
        "measured_value": {"health": sim.current_health, "is_dead": sim.is_dead},
        "target_value": {"health": 100.0, "is_dead": False},
        "details": "Initial health 100/100, alive, no spurious events",
    }

    # Probe 2: Basic damage application
    accepted = sim.apply_damage(25.0)
    p2_pass = (
        accepted is True
        and sim.current_health == 75.0
        and len(sim.health_changed_events) == 1
        and len(sim.damage_accepted_events) == 1
        and sim.death_events == 0
    )
    probe_results["probe_basic_damage"] = {
        "passed": p2_pass,
        "measured_value": sim.current_health,
        "target_value": 75.0,
        "unit": "HP",
        "details": "25 damage reduced health to 75",
    }

    # Probe 3: Invulnerability immediately after accepted hit
    accepted_immediate = sim.apply_damage(20.0)
    p3_pass = (
        accepted_immediate is False
        and sim.current_health == 75.0
        and len(sim.damage_accepted_events) == 1
    )
    probe_results["probe_invulnerability_immediate"] = {
        "passed": p3_pass,
        "measured_value": accepted_immediate,
        "target_value": False,
        "details": "Hit during invulnerability window rejected; health unchanged",
    }

    # Probe 4: Pre-expiry boundary (at t=0.70s < 0.75s)
    sim.advance_time(0.70)
    accepted_pre = sim.apply_damage(20.0)
    p4_pass = (
        accepted_pre is False
        and sim.current_health == 75.0
        and len(sim.damage_accepted_events) == 1
    )
    probe_results["probe_pre_expiry_boundary"] = {
        "passed": p4_pass,
        "measured_value": accepted_pre,
        "target_value": False,
        "details": "Hit at t=0.70s (before 0.75s expiry) rejected",
    }

    # Probe 5: Post-expiry boundary (advance +0.10s -> t=0.80s > 0.75s)
    sim.advance_time(0.10)
    accepted_post = sim.apply_damage(20.0)
    p5_pass = (
        accepted_post is True
        and sim.current_health == 55.0
        and len(sim.damage_accepted_events) == 2
    )
    probe_results["probe_post_expiry_boundary"] = {
        "passed": p5_pass,
        "measured_value": sim.current_health,
        "target_value": 55.0,
        "unit": "HP",
        "details": "Hit at t=0.80s (after 0.75s expiry) accepted; health 55",
    }

    # Probe 6: No timer extension on rejected hits
    # Current hit was at t=0.80s. Window expires at t=1.55s.
    sim.advance_time(0.20)  # t=1.00s
    sim.apply_damage(10.0)  # rejected
    sim.advance_time(0.60)  # t=1.60s (which is > 1.55s, but would be < 1.75s if timer extended!)
    accepted_no_extend = sim.apply_damage(10.0)
    p6_pass = (accepted_no_extend is True and sim.current_health == 45.0)
    probe_results["probe_no_timer_extension"] = {
        "passed": p6_pass,
        "measured_value": accepted_no_extend,
        "target_value": True,
        "details": "Rejected hit during invulnerability did not extend expiry window",
    }

    # Probe 7: Normal healing
    sim.apply_healing(15.0)
    p7_pass = (sim.current_health == 60.0 and len(sim.health_changed_events) == 4)
    probe_results["probe_healing"] = {
        "passed": p7_pass,
        "measured_value": sim.current_health,
        "target_value": 60.0,
        "unit": "HP",
        "details": "Healed 15 HP to 60 HP",
    }

    # Probe 8: Healing clamp to maximum health
    sim.apply_healing(200.0)
    p8_pass = (sim.current_health == 100.0)
    probe_results["probe_healing_clamp"] = {
        "passed": p8_pass,
        "measured_value": sim.current_health,
        "target_value": 100.0,
        "unit": "HP",
        "details": "Healing clamped at maximum health (100.0)",
    }

    # Probe 9: Healing while at maximum health
    ev_count_before = len(sim.health_changed_events)
    heal_full_result = sim.apply_healing(50.0)
    p9_pass = (heal_full_result is False and len(sim.health_changed_events) == ev_count_before)
    probe_results["probe_healing_at_max_health"] = {
        "passed": p9_pass,
        "measured_value": heal_full_result,
        "target_value": False,
        "details": "Healing at full health emitted no health-changed event",
    }

    # Probe 10: Zero damage rejected
    z_res = sim.apply_damage(0.0)
    p10_pass = (z_res is False and sim.current_health == 100.0)
    probe_results["probe_zero_damage"] = {
        "passed": p10_pass,
        "measured_value": z_res,
        "target_value": False,
        "details": "Zero damage rejected without state mutation",
    }

    # Probe 11: Negative damage rejected
    neg_res = sim.apply_damage(-50.0)
    p11_pass = (neg_res is False and sim.current_health == 100.0)
    probe_results["probe_negative_damage"] = {
        "passed": p11_pass,
        "measured_value": neg_res,
        "target_value": False,
        "details": "Negative damage rejected",
    }

    # Probe 12: Non-finite inputs (NaN / Inf) rejected
    nan_res = sim.apply_damage(float("nan"))
    inf_res = sim.apply_damage(float("inf"))
    p12_pass = (nan_res is False and inf_res is False and sim.current_health == 100.0)
    probe_results["probe_non_finite_input"] = {
        "passed": p12_pass,
        "measured_value": False,
        "target_value": False,
        "details": "NaN and Inf damage safely rejected",
    }

    # Probe 13: Lethal damage and event ordering
    sim.advance_time(1.0)  # ensure out of invulnerability
    events_before = len(sim.event_order)
    lethal_res = sim.apply_damage(150.0)
    new_events = sim.event_order[events_before:]
    p13_pass = (
        lethal_res is True
        and sim.current_health == 0.0
        and sim.is_dead is True
        and sim.death_events == 1
        and new_events == ["OnHealthChanged", "OnDamageAccepted", "OnDeath"]
    )
    probe_results["probe_lethal_damage"] = {
        "passed": p13_pass,
        "measured_value": {"health": sim.current_health, "is_dead": sim.is_dead, "event_order": new_events},
        "target_value": {"health": 0.0, "is_dead": True, "event_order": ["OnHealthChanged", "OnDamageAccepted", "OnDeath"]},
        "details": "Lethal damage clamped health to 0, exactly 1 death event emitted in verified order",
    }

    # Probe 14: Repeated damage after death (advance past invulnerability window first)
    sim.advance_time(1.0)
    rep_dead = sim.apply_damage(50.0)
    p14_pass = (rep_dead is False and sim.death_events == 1 and sim.current_health == 0.0)
    probe_results["probe_repeated_damage_after_death"] = {
        "passed": p14_pass,
        "measured_value": sim.death_events,
        "target_value": 1,
        "details": "Damage after death emitted NO duplicate death event",
    }

    # Probe 15: Healing after death rejected (no revival)
    revive_res = sim.apply_healing(50.0)
    p15_pass = (revive_res is False and sim.is_dead is True and sim.current_health == 0.0)
    probe_results["probe_healing_after_death"] = {
        "passed": p15_pass,
        "measured_value": sim.is_dead,
        "target_value": True,
        "details": "Healing after death did not revive character",
    }

    # Probe 16: Reentrancy protection
    sim.is_processing = True
    reentrant_damage = sim.apply_damage(10.0)
    reentrant_heal = sim.apply_healing(10.0)
    sim.is_processing = False
    p16_pass = (reentrant_damage is False and reentrant_heal is False)
    probe_results["probe_callback_reentrancy"] = {
        "passed": p16_pass,
        "measured_value": False,
        "target_value": False,
        "details": "Nested reentrant calls safely rejected",
    }

    return probe_results


if __name__ == "__main__":
    out = run_all_hidden_probes()
    print(json.dumps(out, indent=2))
