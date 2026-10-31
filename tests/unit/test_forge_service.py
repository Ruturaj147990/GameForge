"""Unit tests for ForgeService Qt service (WI-2.8)."""
from pathlib import Path
from PySide6.QtCore import QCoreApplication
import pytest

from src.gameforge_ide.core.events import EventBus
from src.gameforge_ide.desktop.services.forge_service import ForgeService


def test_forge_service_signals_and_active_runs(tmp_path: Path):
    bus = EventBus()
    service = ForgeService(tmp_path, bus=bus)

    events = []
    list_changed_count = [0]

    service.runEvent.connect(lambda ev: events.append(ev))
    service.runListChanged.connect(lambda: list_changed_count.__setitem__(0, list_changed_count[0] + 1))

    # Publish an event
    bus.publish("forge", {"kind": "step_started", "step_id": "test_step", "run_id": "r1"})
    assert len(events) == 1
    assert events[0]["step_id"] == "test_step"
    assert list_changed_count[0] == 0

    # Publish run_started
    bus.publish("forge", {"kind": "run_started", "run_id": "r1"})
    assert len(events) == 2
    assert list_changed_count[0] == 1

    # Publish run_finished
    bus.publish("forge", {"kind": "run_finished", "run_id": "r1", "status": "DONE"})
    assert len(events) == 3
    assert list_changed_count[0] == 2

    service.close()
