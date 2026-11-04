"""Hosted Models settings (Blueprint v2 §6 arrangements, user-facing).

- Profiles: shipped defaults + user override at %APPDATA%/GameForge/hosted_providers.json (no secrets).
- API keys: written ONLY to Windows Credential Manager (target GameForge/<provider_id>); the key field
  is cleared after saving and never logged.
- Workspace opt-in: <workspace>/.gameforge/egress.json.
- Test connection: one tiny, explicitly requested, billed call through the guarded provider.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from ...backend.providers.hosted import (CredentialStore, EgressPolicy, HostedModel, HostedProfile,
                                         PROVIDER_KINDS, GuardedProvider, load_profiles, user_config_dir)


def save_user_profiles(profiles: Dict[str, HostedProfile]) -> Path:
    path = user_config_dir() / "hosted_providers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"providers": []}
    for prof in profiles.values():
        d = asdict(prof)
        d["models"] = [asdict(m) for m in prof.models]
        data["providers"].append(d)
    text = json.dumps(data, indent=1)
    path.write_text(text, encoding="utf-8")
    return path


class HostedSettingsDialog(QDialog):
    def __init__(self, workspace_root: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hosted Models — GameForge")
        self.resize(820, 560)
        self._workspace = Path(workspace_root)
        self._profiles = load_profiles()
        self._creds = CredentialStore()
        self._egress = EgressPolicy(self._workspace)
        self._current = None

        root = QHBoxLayout(self)
        self._list = QListWidget()
        self._list.setMaximumWidth(220)
        for pid in self._profiles:
            self._list.addItem(pid)
        root.addWidget(self._list)

        right = QWidget()
        rv = QVBoxLayout(right)
        form = QFormLayout()
        self._enabled = QCheckBox("Enabled (allows this provider to be used at all)")
        self._optin = QCheckBox(f"Allow for this workspace ({self._workspace.name})")
        self._base_url = QLineEdit()
        self._task_cap = QDoubleSpinBox(); self._task_cap.setRange(0, 1000); self._task_cap.setPrefix("$ ")
        self._day_cap = QDoubleSpinBox(); self._day_cap.setRange(0, 10000); self._day_cap.setPrefix("$ ")
        self._models = QPlainTextEdit()
        self._models.setPlaceholderText('[{"id": "...", "display_name": "...", "max_context": 200000, '
                                        '"usd_per_mtok_in": 0, "usd_per_mtok_out": 0, "roles": ["author"]}]')
        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.Password)
        self._key.setPlaceholderText("Paste API key, then Save key (stored in Windows Credential Manager)")
        self._key_state = QLabel("")
        self._policy = QLabel("")
        self._policy.setWordWrap(True)
        form.addRow(self._enabled)
        form.addRow(self._optin)
        form.addRow("Base URL", self._base_url)
        form.addRow("Per-task cap", self._task_cap)
        form.addRow("Per-day cap", self._day_cap)
        form.addRow("Models (JSON; prices per million tokens are required for metered providers)", self._models)
        key_row = QHBoxLayout()
        key_row.addWidget(self._key, 1)
        self._btn_save_key = QPushButton("Save key")
        self._btn_del_key = QPushButton("Remove key")
        key_row.addWidget(self._btn_save_key)
        key_row.addWidget(self._btn_del_key)
        form.addRow("API key", key_row)
        form.addRow("", self._key_state)
        form.addRow("Data policy", self._policy)
        rv.addLayout(form)
        self._btn_test = QPushButton("Test connection (one tiny billed call)")
        rv.addWidget(self._btn_test)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        rv.addWidget(buttons)
        root.addWidget(right, 1)

        self._list.currentTextChanged.connect(self._load)
        self._btn_save_key.clicked.connect(self._save_key)
        self._btn_del_key.clicked.connect(self._delete_key)
        self._btn_test.clicked.connect(self._test)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _load(self, pid: str) -> None:
        self._commit_form()
        prof = self._profiles.get(pid)
        self._current = pid
        if not prof:
            return
        self._enabled.setChecked(prof.enabled)
        self._optin.setChecked(self._egress.is_allowed(pid))
        self._base_url.setText(prof.base_url)
        self._task_cap.setValue(prof.per_task_usd_cap)
        self._day_cap.setValue(prof.per_day_usd_cap)
        self._models.setPlainText(json.dumps([asdict(m) for m in prof.models], indent=1))
        self._policy.setText(prof.data_policy or "—")
        self._refresh_key_state()

    def _refresh_key_state(self) -> None:
        prof = self._profiles.get(self._current)
        has = bool(prof and self._creds.get(prof))
        self._key_state.setText("Key: stored ✔" if has else "Key: not set")

    def _commit_form(self) -> bool:
        prof = self._profiles.get(self._current) if self._current else None
        if not prof:
            return True
        try:
            models = [HostedModel(**m) for m in json.loads(self._models.toPlainText() or "[]")]
        except (json.JSONDecodeError, TypeError) as exc:
            QMessageBox.warning(self, "Models", f"Models JSON is invalid: {exc}")
            return False
        unpriced = [m.id for m in models if m.usd_per_mtok_in <= 0 and m.usd_per_mtok_out <= 0]
        if self._enabled.isChecked() and not prof.unmetered and (unpriced or not models):
            self._enabled.setChecked(False)
            self._key_state.setText("Not enabled: " + ("add at least one model" if not models else
                                    "set per-million-token prices for " + ", ".join(unpriced)
                                    + " (spend caps cannot be enforced without them)"))
        prof.enabled = self._enabled.isChecked()
        prof.base_url = self._base_url.text().strip()
        prof.per_task_usd_cap = self._task_cap.value()
        prof.per_day_usd_cap = self._day_cap.value()
        prof.models = models
        if self._optin.isChecked():
            self._egress.allow(prof.provider_id)
        else:
            self._egress.revoke(prof.provider_id)
        if self._key.text().strip() and self._current:
            self._save_key()
        return True

    def _save_key(self) -> None:
        secret = self._key.text().strip()
        self._key.clear()  # never keep the secret in the widget
        if not secret or not self._current:
            return
        if not self._creds.set(self._current, secret):
            QMessageBox.warning(self, "API key", "Could not write to Windows Credential Manager.")
        self._refresh_key_state()

    def _delete_key(self) -> None:
        if self._current:
            self._creds.delete(self._current)
            self._refresh_key_state()

    def _save(self) -> None:
        if self._commit_form():
            path = save_user_profiles(self._profiles)
            QMessageBox.information(self, "Hosted Models", f"Saved (no secrets) to {path}")
            self.accept()

    def _test(self) -> None:
        if not self._commit_form():
            return
        prof = self._profiles.get(self._current)
        if not prof or not prof.models:
            QMessageBox.information(self, "Test", "Add at least one model first.")
            return
        cls = PROVIDER_KINDS.get(prof.kind)
        guarded = GuardedProvider(cls(prof), self._workspace)
        try:
            resp = guarded.complete(prof.models[0].id, "Reply with the single word: OK", max_tokens=5)
            QMessageBox.information(self, "Test", f"Response: {resp.content!r}  (cost ${resp.metadata.get('usd', 0):.6f})")
        except Exception as exc:
            QMessageBox.warning(self, "Test", f"Not usable yet: {exc}")
