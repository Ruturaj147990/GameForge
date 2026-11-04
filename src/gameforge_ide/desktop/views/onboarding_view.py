"""Onboarding view module alias for Studio UX (spec §4.10, WI-4.10).

Re-exports OnboardingWizard, EnginePage, PathsPage, and ModelsPage from onboarding.py.
Provides OnboardingView alias for view conventions.
"""
from __future__ import annotations

from .onboarding import (
    EnginePage,
    ModelsPage,
    OnboardingWizard,
    PathsPage,
)

# Canonical view alias
OnboardingView = OnboardingWizard

__all__ = [
    "EnginePage",
    "ModelsPage",
    "OnboardingView",
    "OnboardingWizard",
    "PathsPage",
]
