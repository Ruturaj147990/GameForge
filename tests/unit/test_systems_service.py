"""Unit tests for systems probe functions and SystemsService (WI-4.2)."""

from __future__ import annotations

import time
from pathlib import Path
import pytest
from PySide6.QtCore import QCoreApplication

from src.gameforge_ide.core.systems import (
    SystemRow,
    SystemsSnapshot,
    probe_all,
    probe_ollama,
    probe_engine,
    probe_editor,
    probe_ram,
    probe_disk,
    probe_hosted,
)
from src.gameforge_ide.core.settings import get_settings
from src.gameforge_ide.desktop.services.systems_service import SystemsService


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_systems_snapshot_overall():
    r_ok1 = SystemRow(key="ollama", state="ok", summary="4 models")
    r_ok2 = SystemRow(key="engine", state="ok", summary="UE 5.7.4")
    r_ok3 = SystemRow(key="editor", state="ok", summary="1 active")
    r_ok4 = SystemRow(key="ram", state="ok", summary="30% used")
    r_ok5 = SystemRow(key="disk", state="ok", summary="120 GB free")
    r_ok6 = SystemRow(key="hosted", state="ok", summary="ready")

    # All ok -> overall "ok"
    s_ok = SystemsSnapshot(rows=(r_ok1, r_ok2, r_ok3, r_ok4, r_ok5, r_ok6), taken_at=time.time())
    assert s_ok.overall == "ok"
    assert s_ok.row("ollama") == r_ok1
    assert s_ok.row("nonexistent") is None

    # Engine offline -> overall "offline"
    r_eng_off = SystemRow(key="engine", state="offline", summary="missing", fix_action="set_engine")
    s_eng_off = SystemsSnapshot(rows=(r_ok1, r_eng_off, r_ok3, r_ok4, r_ok5, r_ok6), taken_at=time.time())
    assert s_eng_off.overall == "offline"

    # Ollama offline -> overall "offline"
    r_ol_off = SystemRow(key="ollama", state="offline", summary="offline", fix_action="start_ollama")
    s_ol_off = SystemsSnapshot(rows=(r_ol_off, r_ok2, r_ok3, r_ok4, r_ok5, r_ok6), taken_at=time.time())
    assert s_ol_off.overall == "offline"

    # Disk degraded -> overall "degraded"
    r_disk_deg = SystemRow(key="disk", state="degraded", summary="35 GB free", fix_action=None)
    s_deg = SystemsSnapshot(rows=(r_ok1, r_ok2, r_ok3, r_ok4, r_disk_deg, r_ok6), taken_at=time.time())
    assert s_deg.overall == "degraded"


def test_probe_all_live():
    settings = get_settings()
    snapshot = probe_all(settings=settings, timeout_s=3.0)
    assert isinstance(snapshot, SystemsSnapshot)
    assert len(snapshot.rows) == 6
    keys = {r.key for r in snapshot.rows}
    assert keys == {"ollama", "engine", "editor", "ram", "disk", "hosted"}

    for r in snapshot.rows:
        assert r.state in ("ok", "degraded", "offline", "unknown")
        assert len(r.summary) > 0


def test_systems_service_qt(qapp, tmp_path):
    received = []

    service = SystemsService(workspace_root=tmp_path, auto_start=False)
    service.snapshotChanged.connect(lambda s: received.append(s))

    assert service._timer.interval() == 30_000

    # Minimize window -> interval drops to 120s
    service.set_window_state(visible=True, minimized=True)
    assert service._timer.interval() == 120_000

    # Restore window -> interval returns to 30s
    service.set_window_state(visible=True, minimized=False)
    assert service._timer.interval() == 30_000

    # Hide window -> interval drops to 120s
    service.set_window_state(visible=False, minimized=False)
    assert service._timer.interval() == 120_000

    # Manual refresh
    service.refresh_now()
    # Wait for background job to finish
    deadline = time.time() + 15.0
    while not received and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)

    assert len(received) >= 1
    assert isinstance(received[0], SystemsSnapshot)
    assert service.latest_snapshot == received[0]
    service.stop()
