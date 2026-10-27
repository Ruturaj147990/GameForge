"""Hosted settings dialog: saving profiles never writes a secret to disk."""

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_save_profiles_and_optin_without_secrets(app, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from src.gameforge_ide.backend.providers import hosted
    from src.gameforge_ide.desktop.dialogs import hosted_settings as hs

    stored = {}
    monkeypatch.setattr(hosted.CredentialStore, "set", lambda self, pid, s: stored.__setitem__(pid, s) or True)
    monkeypatch.setattr(hosted.CredentialStore, "get", lambda self, prof: stored.get(prof.provider_id))
    ws = tmp_path / "ws"
    ws.mkdir()
    dlg = hs.HostedSettingsDialog(ws)
    dlg._list.setCurrentRow(0)
    pid = dlg._current
    dlg._models.setPlainText('[{"id": "m", "display_name": "M", "max_context": 1000, "usd_per_mtok_in": 3, "usd_per_mtok_out": 15}]')
    dlg._enabled.setChecked(True)
    dlg._optin.setChecked(True)
    dlg._key.setText("sk-SUPER-SECRET")
    dlg._save_key()
    assert dlg._key.text() == "" and stored[pid] == "sk-SUPER-SECRET"
    assert dlg._commit_form()
    path = hs.save_user_profiles(dlg._profiles)
    saved = path.read_text(encoding="utf-8")
    assert "sk-SUPER-SECRET" not in saved
    assert any(p["provider_id"] == pid and p["enabled"] for p in json.loads(saved)["providers"])
    assert pid in json.loads((ws / ".gameforge" / "egress.json").read_text(encoding="utf-8"))["allowed_providers"]
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert b"sk-SUPER-SECRET" not in f.read_bytes(), f


def test_metered_provider_without_prices_cannot_be_enabled(app, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from src.gameforge_ide.desktop.dialogs import hosted_settings as hs
    ws = tmp_path / "ws"
    ws.mkdir()
    dlg = hs.HostedSettingsDialog(ws)
    dlg._list.setCurrentRow(0)              # shipped "anthropic" profile has no prices
    prof = dlg._profiles[dlg._current]
    assert not prof.unmetered
    dlg._enabled.setChecked(True)
    assert dlg._commit_form()
    assert prof.enabled is False and "prices" in dlg._key_state.text()
    dlg._models.setPlainText('[{"id": "m", "display_name": "M", "max_context": 1000, "usd_per_mtok_in": 3, "usd_per_mtok_out": 15}]')
    dlg._enabled.setChecked(True)
    assert dlg._commit_form() and prof.enabled is True
