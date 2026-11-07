"""Root test configuration and fixtures for GameForge."""
from __future__ import annotations

import os
import sys
import pytest
from PySide6.QtWidgets import QApplication

from src.gameforge_ide.core.jobs import default_job_manager, reset_default_job_manager


@pytest.fixture(scope="session")
def qapp():
    """Session-wide headless QApplication for PySide6 tests."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _cleanup_test_background_jobs():
    """Ensure background jobs started during a test do not leak into subsequent tests."""
    yield
    try:
        reset_default_job_manager(wait=True)
    except Exception:
        pass
