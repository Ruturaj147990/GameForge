"""Placeholder view implementations for Studio UX (WI-4.3).

Each view will be fleshed out in WI-4.4 through WI-4.12.
"""

from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..styles import tokens


class BaseStudioView(QWidget):
    """Base class for Studio UX views."""

    def __init__(self, view_id: str, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.view_id = view_id
        self.setObjectName(f"studioView_{view_id}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        lbl = QLabel(f"Studio View: {title}", self)
        lbl.setObjectName(f"lbl_{view_id}_title")
        lbl.setStyleSheet(f"color: {tokens.TEXT_PRIMARY}; font-size: 18px; font-weight: bold;")
        layout.addWidget(lbl)
        layout.addStretch(1)


from .home_view import HomeView


from .games_view import GamesView


from .design_view import DesignView


from .build_view import BuildView


from .play_view import PlayView


from .evidence_view import EvidenceView


from .assets_view import AssetsView
from .code_view import CodeView
from .settings_view import SettingsView
from .onboarding import OnboardingWizard
from .onboarding_view import OnboardingView


__all__ = [
    "BaseStudioView",
    "HomeView",
    "GamesView",
    "DesignView",
    "BuildView",
    "PlayView",
    "EvidenceView",
    "AssetsView",
    "CodeView",
    "SettingsView",
    "OnboardingWizard",
    "OnboardingView",
]
