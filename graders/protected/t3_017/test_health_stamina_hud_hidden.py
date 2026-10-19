"""GameForge Trusted Hidden Grader Oracle for T3-017 Health and Stamina UMG HUD Widget.

Isolated in graders/protected/t3_017/ and NEVER exposed to candidate agents.
Injected only into isolated grading workspaces to verify HUD binding and event contracts.
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SimulatedHUD:
    displayed_health: float = 100.0
    max_health: float = 100.0
    health_percent: float = 1.0
    displayed_stamina: float = 100.0
    max_stamina: float = 100.0
    stamina_percent: float = 1.0
    bIsDead: bool = False
    bIsBound: bool = False
    event_update_count: int = 0
    subscription_count: int = 0
    bound_player: Optional[Dict[str, Any]] = None

    def bind_to_player(self, player: Optional[Dict[str, Any]]):
        if not player:
            return
        if self.bIsBound:
            self.unbind_from_player()

        self.bound_player = player
        self.bIsBound = True
        self.subscription_count += 1
        self.max_health = player.get("max_health", 100.0)
        self.displayed_health = player.get("current_health", 100.0)
        self.max_stamina = player.get("max_stamina", 100.0)
        self.displayed_stamina = player.get("current_stamina", 100.0)
        self.bIsDead = player.get("is_dead", False)
        self.refresh_display()

    def unbind_from_player(self):
        self.bound_player = None
        self.bIsBound = False
        self.subscription_count = max(0, self.subscription_count - 1)

    def refresh_display(self):
        safe_max_h = max(1.0, self.max_health)
        safe_max_s = max(1.0, self.max_stamina)
        self.health_percent = max(0.0, min(1.0, self.displayed_health / safe_max_h))
        self.stamina_percent = max(0.0, min(1.0, self.displayed_stamina / safe_max_s))

    def on_health_changed(self, new_health: float, delta: float):
        if not self.bIsBound:
            return
        self.displayed_health = new_health
        self.bIsDead = (new_health <= 0.0)
        self.event_update_count += 1
        self.refresh_display()

    def on_stamina_changed(self, new_stamina: float, delta: float):
        if not self.bIsBound:
            return
        self.displayed_stamina = new_stamina
        self.event_update_count += 1
        self.refresh_display()

    def on_death(self):
        if not self.bIsBound:
            return
        self.bIsDead = True
        self.displayed_health = 0.0
        self.event_update_count += 1
        self.refresh_display()


def test_hidden_h1_initial_display():
    player = {"max_health": 100.0, "current_health": 100.0, "max_stamina": 100.0, "current_stamina": 100.0}
    hud = SimulatedHUD()
    hud.bind_to_player(player)
    assert hud.displayed_health == 100.0
    assert hud.health_percent == 1.0
    assert hud.displayed_stamina == 100.0
    assert hud.stamina_percent == 1.0
    assert hud.bIsBound is True


def test_hidden_h2_damage_update():
    player = {"max_health": 100.0, "current_health": 100.0, "max_stamina": 100.0, "current_stamina": 100.0}
    hud = SimulatedHUD()
    hud.bind_to_player(player)
    hud.on_health_changed(50.0, -50.0)
    assert hud.displayed_health == 50.0
    assert abs(hud.health_percent - 0.50) < 0.001


def test_hidden_h3_heal_update():
    player = {"max_health": 100.0, "current_health": 50.0, "max_stamina": 100.0, "current_stamina": 100.0}
    hud = SimulatedHUD()
    hud.bind_to_player(player)
    hud.on_health_changed(75.0, 25.0)
    assert hud.displayed_health == 75.0
    assert abs(hud.health_percent - 0.75) < 0.001


def test_hidden_h4_health_pickup_update():
    player = {"max_health": 100.0, "current_health": 75.0}
    hud = SimulatedHUD()
    hud.bind_to_player(player)
    hud.on_health_changed(100.0, 25.0)
    assert hud.displayed_health == 100.0
    assert abs(hud.health_percent - 1.0) < 0.001


def test_hidden_h5_stamina_pickup_update():
    player = {"max_stamina": 100.0, "current_stamina": 40.0}
    hud = SimulatedHUD()
    hud.bind_to_player(player)
    hud.on_stamina_changed(60.0, 20.0)
    assert hud.displayed_stamina == 60.0
    assert abs(hud.stamina_percent - 0.60) < 0.001


def test_hidden_h6_display_clamping():
    hud = SimulatedHUD()
    hud.max_health = 100.0
    hud.displayed_health = 150.0
    hud.refresh_display()
    assert hud.health_percent == 1.0

    hud.displayed_health = -50.0
    hud.refresh_display()
    assert hud.health_percent == 0.0


def test_hidden_h7_death_state_display():
    player = {"max_health": 100.0, "current_health": 100.0}
    hud = SimulatedHUD()
    hud.bind_to_player(player)
    hud.on_death()
    assert hud.bIsDead is True
    assert hud.displayed_health == 0.0
    assert hud.health_percent == 0.0


def test_hidden_h8_null_player_safety():
    hud = SimulatedHUD()
    hud.bind_to_player(None)
    assert hud.bIsBound is False


def test_hidden_h9_duplicate_subscription_guard():
    player = {"max_health": 100.0, "current_health": 100.0}
    hud = SimulatedHUD()
    hud.bind_to_player(player)
    hud.bind_to_player(player)  # Repeated bind
    initial_updates = hud.event_update_count
    hud.on_health_changed(80.0, -20.0)
    assert (hud.event_update_count - initial_updates) == 1


def test_hidden_h10_clean_unsubscription():
    player = {"max_health": 100.0, "current_health": 100.0}
    hud = SimulatedHUD()
    hud.bind_to_player(player)
    hud.unbind_from_player()
    before = hud.event_update_count
    hud.on_health_changed(50.0, -50.0)
    assert hud.event_update_count == before


def test_hidden_h11_reinitialization():
    player = {"max_health": 100.0, "current_health": 100.0}
    hud = SimulatedHUD()
    hud.bind_to_player(player)
    hud.unbind_from_player()
    hud.bind_to_player(player)
    assert hud.bIsBound is True
    assert hud.displayed_health == 100.0


def test_hidden_h12_rebind_to_new_player():
    player_a = {"max_health": 100.0, "current_health": 100.0}
    player_b = {"max_health": 200.0, "current_health": 150.0}
    hud = SimulatedHUD()
    hud.bind_to_player(player_a)
    hud.bind_to_player(player_b)
    assert hud.max_health == 200.0
    assert hud.displayed_health == 150.0
