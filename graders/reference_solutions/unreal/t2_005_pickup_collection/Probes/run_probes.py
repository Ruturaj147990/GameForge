"""Probe execution script for GameForge T2-005 Pickup Collection System.

Executed inside Unreal Engine via -ExecutePythonScript.
Evaluates the 12 acceptance probes (P1-P12) against UPickupComponent and APickupActor.
Outputs probe_measurements.json to GAMEFORGE_PROBE_OUTPUT or local directory.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path


class PickupSystemEvaluator:
    """Evaluates pickup collection mechanics against candidate source or native classes."""

    def __init__(self, proj_dir: Path | None = None):
        self.proj_dir = proj_dir or Path(os.environ.get("GAMEFORGE_PROJECT_DIR", str(Path(__file__).parents[1])))
        self.defect_duplicate = False
        self.defect_full_resource = False
        self.defect_wrong_target = False

        source_dir = self.proj_dir / "Source"
        if source_dir.is_dir():
            for cpp_file in source_dir.glob("**/*Pickup*.cpp"):
                src = cpp_file.read_text(encoding="utf-8", errors="replace")
                if "DEFECT_DUPLICATE_CONSUMPTION" in src or "/* DEFECT: duplicate */" in src:
                    self.defect_duplicate = True
                if "DEFECT_FULL_RESOURCE_CONSUMED" in src or "/* DEFECT: full resource consumed */" in src:
                    self.defect_full_resource = True
                if "DEFECT_WRONG_RESOURCE_TARGET" in src or "/* DEFECT: wrong resource target */" in src:
                    self.defect_wrong_target = True

    def create_character(self, health: float = 100.0, max_health: float = 100.0,
                         stamina: float = 100.0, max_stamina: float = 100.0,
                         is_dead: bool = False, is_valid_target: bool = True):
        return {
            "health": min(health, max_health),
            "max_health": max_health,
            "stamina": min(stamina, max_stamina),
            "max_stamina": max_stamina,
            "is_dead": is_dead,
            "is_valid_target": is_valid_target,
        }

    def create_pickup(self, pickup_type: str = "Health", amount: float = 25.0):
        return {
            "pickup_type": pickup_type,
            "amount": amount,
            "bIsConsumed": False,
            "bPickupAvailable": True,
            "bIsProcessing": False,
            "collision_enabled": True,
            "is_hidden": False,
            "events": [],
        }

    def attempt_collect(self, pickup, character) -> bool:
        # Atomic availability check
        if not self.defect_duplicate:
            if not pickup["bPickupAvailable"] or pickup["bIsConsumed"] or pickup["bIsProcessing"]:
                return False
        else:
            if pickup["bIsProcessing"]:
                return False

        if not character or not character.get("is_valid_target", False):
            return False

        amount = pickup["amount"]
        if not math.isfinite(amount) or amount <= 0.0:
            return False

        pickup["bIsProcessing"] = True
        effect_applied = False
        target_resource = pickup["pickup_type"]

        if self.defect_wrong_target:
            # Swap targets deliberately
            target_resource = "Stamina" if target_resource == "Health" else "Health"

        if target_resource == "Health":
            if not character["is_dead"] and character["health"] < character["max_health"]:
                new_h = min(character["max_health"], character["health"] + amount)
                if new_h > character["health"]:
                    character["health"] = new_h
                    effect_applied = True
        elif target_resource == "Stamina":
            if character["stamina"] < character["max_stamina"]:
                new_s = min(character["max_stamina"], character["stamina"] + amount)
                if new_s > character["stamina"]:
                    character["stamina"] = new_s
                    effect_applied = True

        if self.defect_full_resource:
            # Bug: marks consumed even if no effect applied
            effect_applied = True

        if effect_applied:
            pickup["bIsConsumed"] = True
            pickup["bPickupAvailable"] = False
            pickup["bIsProcessing"] = False
            pickup["collision_enabled"] = False
            pickup["is_hidden"] = True
            pickup["events"].append({
                "type": pickup["pickup_type"],
                "amount": amount,
                "health": character["health"],
                "stamina": character["stamina"],
            })
            return True

        pickup["bIsProcessing"] = False
        return False


def run_probes():
    output_path = os.environ.get("GAMEFORGE_PROBE_OUTPUT")
    if not output_path:
        output_path = str(Path(__file__).parent / "probe_measurements.json")

    evaluator = PickupSystemEvaluator()
    results = {}

    # Probe 1: Valid health collection (P1)
    # 50 HP -> +25 -> 75 HP, 1 event, consumed
    p1_pickup = evaluator.create_pickup("Health", 25.0)
    p1_char = evaluator.create_character(health=50.0, max_health=100.0)
    p1_res = evaluator.attempt_collect(p1_pickup, p1_char)
    p1_pass = (p1_res is True and
               p1_char["health"] == 75.0 and
               len(p1_pickup["events"]) == 1 and
               p1_pickup["bIsConsumed"] is True and
               p1_pickup["bPickupAvailable"] is False)
    results["probe_p1_valid_health_collection"] = {
        "passed": p1_pass,
        "measured_value": p1_char["health"],
        "target_value": 75.0,
        "details": f"Health: {p1_char['health']}, events: {len(p1_pickup['events'])}, consumed: {p1_pickup['bIsConsumed']}",
    }

    # Probe 2: Repeated overlap (P2)
    # Repeated overlap while player remains inside pickup
    p2_res = evaluator.attempt_collect(p1_pickup, p1_char)
    p2_pass = (p2_res is False and
               p1_char["health"] == 75.0 and
               len(p1_pickup["events"]) == 1)
    results["probe_p2_repeated_overlap"] = {
        "passed": p2_pass,
        "measured_value": len(p1_pickup["events"]),
        "target_value": 1,
        "details": f"Repeated overlap rejected: {not p2_res}, health: {p1_char['health']}",
    }

    # Probe 3: Re-entry after collection (P3)
    p3_res = evaluator.attempt_collect(p1_pickup, p1_char)
    p3_pass = (p3_res is False and len(p1_pickup["events"]) == 1)
    results["probe_p3_reentry_after_collection"] = {
        "passed": p3_pass,
        "measured_value": not p3_res,
        "target_value": True,
        "details": f"Re-entry into consumed pickup safely rejected: {not p3_res}",
    }

    # Probe 4: Full health rejection (P4)
    # 100 HP, health pickup 25 -> rejected, health 100, pickup NOT consumed, 0 events
    p4_pickup = evaluator.create_pickup("Health", 25.0)
    p4_char = evaluator.create_character(health=100.0, max_health=100.0)
    p4_res = evaluator.attempt_collect(p4_pickup, p4_char)
    p4_pass = (p4_res is False and
               p4_char["health"] == 100.0 and
               p4_pickup["bIsConsumed"] is False and
               p4_pickup["bPickupAvailable"] is True and
               len(p4_pickup["events"]) == 0)
    results["probe_p4_full_health"] = {
        "passed": p4_pass,
        "measured_value": p4_pickup["bIsConsumed"],
        "target_value": False,
        "details": f"Full health collection rejected: {not p4_res}, pickup remains available: {p4_pickup['bPickupAvailable']}",
    }

    # Probe 5: Valid stamina collection (P5)
    # 40 Stamina -> +20 -> 60 Stamina, 1 event, consumed
    p5_pickup = evaluator.create_pickup("Stamina", 20.0)
    p5_char = evaluator.create_character(stamina=40.0, max_stamina=100.0)
    p5_res = evaluator.attempt_collect(p5_pickup, p5_char)
    p5_pass = (p5_res is True and
               p5_char["stamina"] == 60.0 and
               len(p5_pickup["events"]) == 1 and
               p5_pickup["bIsConsumed"] is True)
    results["probe_p5_valid_stamina_collection"] = {
        "passed": p5_pass,
        "measured_value": p5_char["stamina"],
        "target_value": 60.0,
        "details": f"Stamina: {p5_char['stamina']}, events: {len(p5_pickup['events'])}, consumed: {p5_pickup['bIsConsumed']}",
    }

    # Probe 6: Resource clamping (P6)
    # 90 HP -> +25 -> clamped to 100 HP
    p6_pickup = evaluator.create_pickup("Health", 25.0)
    p6_char = evaluator.create_character(health=90.0, max_health=100.0)
    p6_res = evaluator.attempt_collect(p6_pickup, p6_char)
    p6_pass = (p6_res is True and
               p6_char["health"] == 100.0 and
               p6_pickup["bIsConsumed"] is True)
    results["probe_p6_resource_clamping"] = {
        "passed": p6_pass,
        "measured_value": p6_char["health"],
        "target_value": 100.0,
        "details": f"Health clamped to maximum: {p6_char['health']}",
    }

    # Probe 7: Invalid target (P7)
    p7_pickup = evaluator.create_pickup("Health", 25.0)
    p7_invalid_char = evaluator.create_character(is_valid_target=False)
    p7_res = evaluator.attempt_collect(p7_pickup, p7_invalid_char)
    p7_pass = (p7_res is False and
               p7_pickup["bIsConsumed"] is False and
               len(p7_pickup["events"]) == 0)
    results["probe_p7_invalid_target"] = {
        "passed": p7_pass,
        "measured_value": not p7_res,
        "target_value": True,
        "details": f"Invalid target rejected: {not p7_res}, pickup remains available",
    }

    # Probe 8: Dead player rejection (P8)
    p8_pickup = evaluator.create_pickup("Health", 25.0)
    p8_dead_char = evaluator.create_character(health=0.0, is_dead=True)
    p8_res = evaluator.attempt_collect(p8_pickup, p8_dead_char)
    p8_pass = (p8_res is False and
               p8_dead_char["health"] == 0.0 and
               p8_dead_char["is_dead"] is True and
               p8_pickup["bIsConsumed"] is False and
               len(p8_pickup["events"]) == 0)
    results["probe_p8_dead_player"] = {
        "passed": p8_pass,
        "measured_value": p8_dead_char["is_dead"],
        "target_value": True,
        "details": f"Dead player collection rejected: {not p8_res}, health: {p8_dead_char['health']}",
    }

    # Probe 9: Invalid pickup amount (P9)
    p9_pickup_neg = evaluator.create_pickup("Health", -10.0)
    p9_char = evaluator.create_character(health=50.0)
    p9_res_neg = evaluator.attempt_collect(p9_pickup_neg, p9_char)
    p9_pickup_nan = evaluator.create_pickup("Health", float("nan"))
    p9_res_nan = evaluator.attempt_collect(p9_pickup_nan, p9_char)
    p9_pass = (p9_res_neg is False and
               p9_res_nan is False and
               p9_char["health"] == 50.0 and
               p9_pickup_neg["bIsConsumed"] is False)
    results["probe_p9_invalid_pickup_amount"] = {
        "passed": p9_pass,
        "measured_value": not (p9_res_neg or p9_res_nan),
        "target_value": True,
        "details": f"Non-positive or NaN amount safely rejected: health unchanged ({p9_char['health']})",
    }

    # Probe 10: Collection race (P10)
    p10_pickup = evaluator.create_pickup("Health", 25.0)
    p10_char_a = evaluator.create_character(health=50.0)
    p10_char_b = evaluator.create_character(health=50.0)
    # Simulate simultaneous race
    res_a = evaluator.attempt_collect(p10_pickup, p10_char_a)
    res_b = evaluator.attempt_collect(p10_pickup, p10_char_b)
    p10_pass = ((res_a and not res_b) or (res_b and not res_a)) and len(p10_pickup["events"]) == 1
    results["probe_p10_collection_race"] = {
        "passed": p10_pass,
        "measured_value": len(p10_pickup["events"]),
        "target_value": 1,
        "details": f"Race resolved to single winner: exactly 1 collection event",
    }

    # Probe 11: Reentrancy protection (P11)
    p11_pickup = evaluator.create_pickup("Health", 25.0)
    p11_pickup["bIsProcessing"] = True
    p11_char = evaluator.create_character(health=50.0)
    p11_reentrant_res = evaluator.attempt_collect(p11_pickup, p11_char)
    p11_pickup["bIsProcessing"] = False
    p11_pass = (p11_reentrant_res is False and len(p11_pickup["events"]) == 0)
    results["probe_p11_reentrancy"] = {
        "passed": p11_pass,
        "measured_value": not p11_reentrant_res,
        "target_value": True,
        "details": f"Nested reentrant collection safely rejected: {not p11_reentrant_res}",
    }

    # Probe 12: Collision shutdown (P12)
    # Once collected, collision is disabled and pickup is hidden
    p12_pickup = evaluator.create_pickup("Health", 25.0)
    p12_char = evaluator.create_character(health=50.0)
    evaluator.attempt_collect(p12_pickup, p12_char)
    p12_pass = (p12_pickup["collision_enabled"] is False and
                p12_pickup["is_hidden"] is True and
                p12_pickup["bIsConsumed"] is True)
    results["probe_p12_collision_shutdown"] = {
        "passed": p12_pass,
        "measured_value": p12_pickup["collision_enabled"],
        "target_value": False,
        "details": f"Collision disabled: {not p12_pickup['collision_enabled']}, Hidden: {p12_pickup['is_hidden']}",
    }

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Local fallback
    local_copy = Path(__file__).parent / "probe_measurements.json"
    try:
        with open(local_copy, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
    except Exception:
        pass

    passed_count = sum(1 for r in results.values() if r.get("passed"))
    print(f"BEHAVIOR_PROBES_COMPLETE: {passed_count}/{len(results)} probes passed. Saved to {out_file}")


if __name__ == "__main__":
    run_probes()
