"""
src/gameforge_ide/desktop/dialogs/ollama_setup.py
Ollama Local Service Setup Dialog (WI-4.4).
Provides interactive service management, automatic detection, one-click start, and status monitoring.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.settings import get_settings
from ..styles import tokens


def find_ollama_executable() -> Optional[Path]:
    """Discover the Ollama executable on the host system without hardcoded drive literals."""
    # 1. System PATH
    found = shutil.which("ollama")
    if found:
        return Path(found).resolve()

    # 2. Host profile or settings
    profile = get_settings().host_profile
    if profile.get("ollama_bin"):
        p = Path(profile["ollama_bin"])
        if p.is_file():
            return p.resolve()

    models_dir = profile.get("ollama_models_dir")
    if models_dir:
        parent_dir = Path(models_dir).parent
        cand = parent_dir / "ollama_bin" / "ollama.exe"
        if cand.is_file():
            return cand.resolve()

    # 3. Standard Windows LocalAppData user install
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        std_win = Path(local_app) / "Programs" / "Ollama" / "ollama.exe"
        if std_win.is_file():
            return std_win.resolve()

    # 4. Standard Windows 64-bit Program Files install
    prog_files = os.environ.get("ProgramFiles")
    if prog_files:
        std_pf = Path(prog_files) / "Ollama" / "ollama.exe"
        if std_pf.is_file():
            return std_pf.resolve()

    return None


def get_ollama_models_directory() -> Optional[Path]:
    """Resolve models directory from environment or host profile."""
    env_dir = os.environ.get("OLLAMA_MODELS")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir).resolve()
    profile = get_settings().host_profile
    prof_models = profile.get("ollama_models_dir")
    if prof_models and Path(prof_models).is_dir():
        return Path(prof_models).resolve()
    return None


def check_ollama_status(url: str = "http://127.0.0.1:11434", timeout_s: float = 1.5) -> Tuple[bool, List[str]]:
    """Probe Ollama tags endpoint to determine connectivity and available models."""
    try:
        clean_url = url.rstrip("/")
        req = urllib.request.Request(f"{clean_url}/api/tags", headers={"User-Agent": "GameForge-IDE"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [
                    m.get("name", "")
                    for m in (data.get("models") or [])
                    if isinstance(m, dict) and m.get("name")
                ]
                return True, models
    except Exception:
        pass
    return False, []


def start_ollama_service(ollama_exe: Path) -> bool:
    """Launch Ollama serve as a detached background process."""
    env = os.environ.copy()
    models_dir = get_ollama_models_directory()
    if models_dir:
        env["OLLAMA_MODELS"] = str(models_dir)

    creationflags = 0
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NO_WINDOW
        creationflags = 0x00000008 | 0x08000000

    try:
        subprocess.Popen(
            [str(ollama_exe), "serve"],
            env=env,
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


class OllamaSetupDialog(QDialog):
    """Interactive setup dialog for local Ollama LLM provider."""

    serviceStarted = Signal()
    settingsRequested = Signal()

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        systems_service: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ollamaSetupDialog")
        self.setWindowTitle("Ollama Setup — GameForge")
        self.setMinimumWidth(540)
        self.resize(560, 440)

        self._workspace = workspace_root
        self._systems_service = systems_service
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._on_poll_tick)
        self._poll_attempts = 0

        self._settings = get_settings()
        self._ollama_url = getattr(self._settings, "ollama_url", "http://127.0.0.1:11434")
        self._exe_path = find_ollama_executable()
        self._models_dir = get_ollama_models_directory()

        self._build_ui()
        self._refresh_status()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(tokens.SPACE_MD)

        # Header Title
        title_lbl = QLabel("Local Ollama LLM Service", self)
        title_lbl.setStyleSheet(
            f"font-size: {tokens.FONT_HEADING}px; font-weight: bold; color: {tokens.TEXT_PRIMARY};"
        )
        root.addWidget(title_lbl)

        # Subtitle
        sub_lbl = QLabel(
            "GameForge uses local Ollama to run reasoning, design planning, and tool orchestration "
            "directly on your AMD GPU/CPU with zero cloud subscriptions or data egress.",
            self,
        )
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet(f"font-size: {tokens.FONT_BODY}px; color: {tokens.TEXT_SECONDARY};")
        root.addWidget(sub_lbl)

        # Status Card Box
        self._status_card = QFrame(self)
        self._status_card.setStyleSheet(
            f"QFrame {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 12px;"
            f"}}"
        )
        sc_layout = QHBoxLayout(self._status_card)
        sc_layout.setContentsMargins(12, 10, 12, 10)
        sc_layout.setSpacing(tokens.SPACE_SM)

        self._dot_lbl = QLabel("●", self._status_card)
        self._dot_lbl.setStyleSheet(f"font-size: 14px; color: {tokens.ACCENT_ERROR};")
        sc_layout.addWidget(self._dot_lbl)

        self._status_text_lbl = QLabel("Checking Ollama status...", self._status_card)
        self._status_text_lbl.setStyleSheet(
            f"font-size: {tokens.FONT_BODY}px; font-weight: 600; color: {tokens.TEXT_PRIMARY};"
        )
        sc_layout.addWidget(self._status_text_lbl, 1)

        root.addWidget(self._status_card)

        # Configuration Details Form
        form_frame = QFrame(self)
        form_frame.setStyleSheet(
            f"QFrame {{"
            f"  background-color: {tokens.BG_PANEL};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 12px;"
            f"}}"
        )
        form = QFormLayout(form_frame)
        form.setContentsMargins(12, 10, 12, 10)
        form.setSpacing(tokens.SPACE_SM)

        url_val = QLabel(self._ollama_url, form_frame)
        url_val.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY_SM}px;")
        form.addRow(QLabel("Service URL:", form_frame), url_val)

        exe_str = str(self._exe_path) if self._exe_path else "Not detected in PATH or standard locations"
        self._exe_val = QLabel(exe_str, form_frame)
        self._exe_val.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY if self._exe_path else tokens.ACCENT_WARNING}; "
            f"font-size: {tokens.FONT_BODY_SM}px;"
        )
        form.addRow(QLabel("Executable:", form_frame), self._exe_val)

        models_str = str(self._models_dir) if self._models_dir else "Default (~/.ollama/models)"
        models_val = QLabel(models_str, form_frame)
        models_val.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: {tokens.FONT_BODY_SM}px;")
        form.addRow(QLabel("Models Dir:", form_frame), models_val)

        root.addWidget(form_frame)

        root.addStretch(1)

        # Action Buttons Layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(tokens.SPACE_SM)

        self._btn_start = QPushButton("▶ Start Ollama Service", self)
        self._btn_start.setObjectName("btn_start_ollama")
        self._btn_start.setCursor(Qt.PointingHandCursor)
        self._btn_start.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.ACCENT_PRIMARY};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: none;"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 8px 16px;"
            f"  font-weight: 600;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {tokens.ACCENT_HOVER};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background-color: {tokens.BG_ACTIVE};"
            f"  color: {tokens.TEXT_SECONDARY};"
            f"}}"
        )
        self._btn_start.clicked.connect(self._on_start_clicked)
        btn_layout.addWidget(self._btn_start)

        self._btn_settings = QPushButton("⚙ Configure Settings", self)
        self._btn_settings.setObjectName("btn_open_settings")
        self._btn_settings.setCursor(Qt.PointingHandCursor)
        self._btn_settings.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 8px 14px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"}}"
        )
        self._btn_settings.clicked.connect(self._on_settings_clicked)
        btn_layout.addWidget(self._btn_settings)

        self._btn_download = QPushButton("🌐 Download Ollama", self)
        self._btn_download.setCursor(Qt.PointingHandCursor)
        self._btn_download.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: transparent;"
            f"  color: {tokens.ACCENT_HOVER};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 8px 14px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"}}"
        )
        self._btn_download.clicked.connect(self._on_download_clicked)
        self._btn_download.setVisible(self._exe_path is None)
        btn_layout.addWidget(self._btn_download)

        btn_layout.addStretch(1)

        self._btn_close = QPushButton("Close", self)
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {tokens.BG_SURFACE};"
            f"  color: {tokens.TEXT_SECONDARY};"
            f"  border: 1px solid {tokens.BORDER};"
            f"  border-radius: {tokens.RADIUS}px;"
            f"  padding: 8px 16px;"
            f"  font-size: {tokens.FONT_BODY}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {tokens.BG_HOVER};"
            f"  color: {tokens.TEXT_PRIMARY};"
            f"}}"
        )
        self._btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self._btn_close)

        root.addLayout(btn_layout)

    def _refresh_status(self) -> None:
        online, models = check_ollama_status(self._ollama_url, timeout_s=1.0)
        if online:
            count = len(models)
            model_info = f"{count} model{'s' if count != 1 else ''} loaded"
            self._dot_lbl.setStyleSheet(f"font-size: 14px; color: {tokens.ACCENT_SUCCESS};")
            self._status_text_lbl.setText(f"Online — {model_info}")
            self._btn_start.setText("✔ Ollama Service Running")
            self._btn_start.setEnabled(False)
        else:
            self._dot_lbl.setStyleSheet(f"font-size: 14px; color: {tokens.ACCENT_ERROR};")
            self._status_text_lbl.setText("Offline — service not reachable")
            if self._exe_path:
                self._btn_start.setText("▶ Start Ollama Service")
                self._btn_start.setEnabled(True)
            else:
                self._btn_start.setText("Ollama Not Installed")
                self._btn_start.setEnabled(False)
                self._btn_download.setVisible(True)

    @Slot()
    def _on_start_clicked(self) -> None:
        if not self._exe_path:
            return

        self._btn_start.setEnabled(False)
        self._btn_start.setText("Starting Ollama service...")
        self._status_text_lbl.setText("Launching local daemon process...")

        ok = start_ollama_service(self._exe_path)
        if not ok:
            self._status_text_lbl.setText("Failed to spawn Ollama process.")
            self._btn_start.setEnabled(True)
            self._btn_start.setText("▶ Retry Start")
            return

        self._poll_attempts = 0
        self._poll_timer.start()

    @Slot()
    def _on_poll_tick(self) -> None:
        self._poll_attempts += 1
        online, models = check_ollama_status(self._ollama_url, timeout_s=0.5)
        if online:
            self._poll_timer.stop()
            count = len(models)
            self._dot_lbl.setStyleSheet(f"font-size: 14px; color: {tokens.ACCENT_SUCCESS};")
            self._status_text_lbl.setText(f"Online — {count} model{'s' if count != 1 else ''} ready!")
            self._btn_start.setText("✔ Service Started")
            self._btn_start.setEnabled(False)

            self.serviceStarted.emit()
            if self._systems_service:
                self._systems_service.refresh_now()
        elif self._poll_attempts >= 20:  # 10 seconds timeout
            self._poll_timer.stop()
            self._status_text_lbl.setText("Service started but not responding yet. Check port 11434.")
            self._btn_start.setEnabled(True)
            self._btn_start.setText("▶ Retry Check")

    @Slot()
    def _on_settings_clicked(self) -> None:
        self.settingsRequested.emit()
        self.accept()

    @Slot()
    def _on_download_clicked(self) -> None:
        QDesktopServices.openUrl(QUrl("https://ollama.com/download"))

    def reject(self) -> None:
        if hasattr(self, "_poll_timer") and self._poll_timer.isActive():
            self._poll_timer.stop()
        super().reject()

    def accept(self) -> None:
        if hasattr(self, "_poll_timer") and self._poll_timer.isActive():
            self._poll_timer.stop()
        super().accept()

    def closeEvent(self, event) -> None:
        if hasattr(self, "_poll_timer") and self._poll_timer.isActive():
            self._poll_timer.stop()
        super().closeEvent(event)
