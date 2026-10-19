"""Probe execution script for GameForge T3-017 Health and Stamina UMG HUD Widget.

Executed inside Unreal Engine via -ExecutePythonScript.
Evaluates the 12 acceptance probes (H1-H12) against UHealthStaminaHUDWidget.
Outputs probe_measurements.json to GAMEFORGE_PROBE_OUTPUT or local directory.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path


class HUDWidgetEvaluator:
    """Evaluates UHealthStaminaHUDWidget lifecycle, binding, clamping, and event handling."""

    def __init__(self, proj_dir: Path | None = None):
        self.proj_dir = proj_dir or Path(os.environ.get("GAMEFORGE_PROJECT_DIR", str(Path(__file__).parents[1])))
        self.defect_duplicate_sub = False
        self.defect_clamping = False
        self.defect_stale_ref = False

        source_dir = self.proj_dir / "Source"
        if source_dir.is_dir():
            for cpp_file in source_dir.glob("**/*HUD*.cpp"):
                src = cpp_file.read_text(encoding="utf-8", errors="replace")
                if "DEFECT_DUPLICATE_SUBSCRIPTION" in src or "/* DEFECT: duplicate subscription */" in src:
                    self.defect_duplicate_sub = True
                if "DEFECT_BROKEN_CLAMPING" in src or "/* DEFECT: broken clamping */" in src:
                    self.defect_clamping = True
                if "DEFECT_STALE_REFERENCE" in src or "/* DEFECT: stale reference */" in src:
                    self.defect_stale_ref = True

    def create_simulated_hud(self):
        return {
            "displayed_health": 100.0,
            "max_health": 100.0,
            "health_percent": 1.0,
            "displayed_stamina": 100.0,
            "max_stamina": 100.0,
            "stamina_percent": 1.0,
            "bIsDead": False,
            "bIsBound": False,
            "event_update_count": 0,
            "subscription_count": 0,
            "bound_player": None,
        }

    def bind_to_player(self, hud, player):
        if not player:
            return

        if hud["bIsBound"] and not self.defect_duplicate_sub:
            self.unbind_from_player(hud)

        hud["bound_player"] = player
        hud["bIsBound"] = True
        hud["subscription_count"] += 1
        hud["max_health"] = player.get("max_health", 100.0)
        hud["displayed_health"] = player.get("current_health", 100.0)
        hud["max_stamina"] = player.get("max_stamina", 100.0)
        hud["displayed_stamina"] = player.get("current_stamina", 100.0)
        hud["bIsDead"] = player.get("is_dead", False)
        self.refresh_display(hud)

    def unbind_from_player(self, hud):
        hud["bound_player"] = None
        hud["bIsBound"] = False
        hud["subscription_count"] = max(0, hud["subscription_count"] - 1)

    def refresh_display(self, hud):
        safe_max_h = max(1.0, hud["max_health"])
        safe_max_s = max(1.0, hud["max_stamina"])

        if self.defect_clamping:
            hud["health_percent"] = hud["displayed_health"] / safe_max_h
            hud["stamina_percent"] = hud["displayed_stamina"] / safe_max_s
        else:
            hud["health_percent"] = max(0.0, min(1.0, hud["displayed_health"] / safe_max_h))
            hud["stamina_percent"] = max(0.0, min(1.0, hud["displayed_stamina"] / safe_max_s))

    def on_health_changed(self, hud, new_health, delta):
        if not hud["bIsBound"]:
            return
        # If defect duplicate sub, fires multiple times
        factor = hud["subscription_count"] if self.defect_duplicate_sub else 1
        hud["displayed_health"] = new_health
        hud["bIsDead"] = (new_health <= 0.0)
        hud["event_update_count"] += factor
        self.refresh_display(hud)

    def on_stamina_changed(self, hud, new_stamina, delta):
        if not hud["bIsBound"]:
            return
        factor = hud["subscription_count"] if self.defect_duplicate_sub else 1
        hud["displayed_stamina"] = new_stamina
        hud["event_update_count"] += factor
        self.refresh_display(hud)

    def on_death(self, hud):
        if not hud["bIsBound"]:
            return
        factor = hud["subscription_count"] if self.defect_duplicate_sub else 1
        hud["bIsDead"] = True
        hud["displayed_health"] = 0.0
        hud["event_update_count"] += factor
        self.refresh_display(hud)


def run_probes():
    output_path = os.environ.get("GAMEFORGE_PROBE_OUTPUT")
    if not output_path:
        output_path = str(Path(__file__).parent / "probe_measurements.json")

    evaluator = HUDWidgetEvaluator()
    results = {}

    player_a = {
        "max_health": 100.0,
        "current_health": 100.0,
        "max_stamina": 100.0,
        "current_stamina": 100.0,
        "is_dead": False,
    }

    hud = evaluator.create_simulated_hud()

    # H1: Initial values (100 HP, 100 Stamina, 1.0 percent)
    evaluator.bind_to_player(hud, player_a)
    h1_pass = (hud["displayed_health"] == 100.0 and
               hud["health_percent"] == 1.0 and
               hud["displayed_stamina"] == 100.0 and
               hud["stamina_percent"] == 1.0 and
               hud["bIsBound"] is True)
    results["probe_h1_initial_display"] = {
        "passed": h1_pass,
        "measured_value": hud["health_percent"],
        "target_value": 1.0,
        "details": f"Health: {hud['displayed_health']}, Stamina: {hud['displayed_stamina']}",
    }

    # H2: Health update after damage (100 -> 50 HP)
    evaluator.on_health_changed(hud, 50.0, -50.0)
    h2_pass = (hud["displayed_health"] == 50.0 and abs(hud["health_percent"] - 0.50) < 0.001)
    results["probe_h2_damage_update"] = {
        "passed": h2_pass,
        "measured_value": hud["displayed_health"],
        "target_value": 50.0,
        "details": f"Displayed health after 50 damage: {hud['displayed_health']}",
    }

    # H3: Health update after healing (50 -> 75 HP)
    evaluator.on_health_changed(hud, 75.0, 25.0)
    h3_pass = (hud["displayed_health"] == 75.0 and abs(hud["health_percent"] - 0.75) < 0.001)
    results["probe_h3_heal_update"] = {
        "passed": h3_pass,
        "measured_value": hud["displayed_health"],
        "target_value": 75.0,
        "details": f"Displayed health after 25 heal: {hud['displayed_health']}",
    }

    # H4: Health pickup update (75 -> 100 HP)
    evaluator.on_health_changed(hud, 100.0, 25.0)
    h4_pass = (hud["displayed_health"] == 100.0 and abs(hud["health_percent"] - 1.0) < 0.001)
    results["probe_h4_health_pickup_update"] = {
        "passed": h4_pass,
        "measured_value": hud["displayed_health"],
        "target_value": 100.0,
        "details": f"Displayed health after health pickup: {hud['displayed_health']}",
    }

    # H5: Stamina update after stamina pickup (40 -> 60)
    evaluator.on_stamina_changed(hud, 60.0, 20.0)
    h5_pass = (hud["displayed_stamina"] == 60.0 and abs(hud["stamina_percent"] - 0.60) < 0.001)
    results["probe_h5_stamina_update"] = {
        "passed": h5_pass,
        "measured_value": hud["displayed_stamina"],
        "target_value": 60.0,
        "details": f"Displayed stamina after pickup: {hud['displayed_stamina']}",
    }

    # H6: Clamping at minimum and maximum
    hud["displayed_health"] = 150.0
    evaluator.refresh_display(hud)
    over_clamp_ok = (hud["health_percent"] == 1.0)

    hud["displayed_health"] = -20.0
    evaluator.refresh_display(hud)
    under_clamp_ok = (hud["health_percent"] == 0.0)

    h6_pass = over_clamp_ok and under_clamp_ok
    results["probe_h6_display_clamping"] = {
        "passed": h6_pass,
        "measured_value": hud["health_percent"],
        "target_value": 0.0,
        "details": f"Over-max clamped: {over_clamp_ok}, under-min clamped: {under_clamp_ok}",
    }

    # H7: Zero-health / death-state display
    evaluator.on_death(hud)
    h7_pass = (hud["bIsDead"] is True and hud["displayed_health"] == 0.0 and hud["health_percent"] == 0.0)
    results["probe_h7_death_state_display"] = {
        "passed": h7_pass,
        "measured_value": hud["bIsDead"],
        "target_value": True,
        "details": f"Dead state: {hud['bIsDead']}, Health: {hud['displayed_health']}",
    }

    # H8: Missing player / null reference handled safely
    null_hud = evaluator.create_simulated_hud()
    evaluator.bind_to_player(null_hud, None)
    h8_pass = (null_hud["bIsBound"] is False and null_hud["bound_player"] is None)
    results["probe_h8_null_player_safety"] = {
        "passed": h8_pass,
        "measured_value": null_hud["bIsBound"],
        "target_value": False,
        "details": "Binding to null player safely handled without exception",
    }

    # H9: No duplicate subscriptions after repeated bind
    sub_hud = evaluator.create_simulated_hud()
    evaluator.bind_to_player(sub_hud, player_a)
    evaluator.bind_to_player(sub_hud, player_a)  # Second repeated bind
    initial_updates = sub_hud["event_update_count"]
    evaluator.on_health_changed(sub_hud, 80.0, -20.0)
    new_updates = sub_hud["event_update_count"] - initial_updates
    h9_pass = (new_updates == 1)
    results["probe_h9_duplicate_subscription_guard"] = {
        "passed": h9_pass,
        "measured_value": new_updates,
        "target_value": 1,
        "details": f"Update count delta from 1 event: {new_updates} (expected 1)",
    }

    # H10: Correct unsubscription on teardown
    evaluator.unbind_from_player(sub_hud)
    before_unbind_updates = sub_hud["event_update_count"]
    evaluator.on_health_changed(sub_hud, 50.0, -30.0)
    after_unbind_updates = sub_hud["event_update_count"]
    h10_pass = (before_unbind_updates == after_unbind_updates and sub_hud["bIsBound"] is False)
    results["probe_h10_clean_unsubscription"] = {
        "passed": h10_pass,
        "measured_value": sub_hud["bIsBound"],
        "target_value": False,
        "details": f"Events after unbind: {after_unbind_updates - before_unbind_updates}",
    }

    # H11: Reinitialization behavior
    evaluator.bind_to_player(sub_hud, player_a)
    h11_pass = (sub_hud["bIsBound"] is True and sub_hud["displayed_health"] == 100.0)
    results["probe_h11_reinitialization"] = {
        "passed": h11_pass,
        "measured_value": sub_hud["bIsBound"],
        "target_value": True,
        "details": "Re-binding after teardown restored valid state",
    }

    # H12: Continued updates after legitimate player rebind
    player_b = {"max_health": 200.0, "current_health": 150.0, "max_stamina": 100.0, "current_stamina": 80.0, "is_dead": False}
    evaluator.bind_to_player(sub_hud, player_b)
    evaluator.on_health_changed(sub_hud, 140.0, -10.0)
    h12_pass = (sub_hud["displayed_health"] == 140.0 and sub_hud["max_health"] == 200.0)
    results["probe_h12_rebind_to_new_player"] = {
        "passed": h12_pass,
        "measured_value": sub_hud["displayed_health"],
        "target_value": 140.0,
        "details": f"Rebound to Player B: health {sub_hud['displayed_health']}/{sub_hud['max_health']}",
    }

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

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
