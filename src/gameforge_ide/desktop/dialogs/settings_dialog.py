"""GameForge IDE — Settings Dialog Compatibility Module.

Redirects SettingsDialog alias to HostedSettingsDialog.
"""

from __future__ import annotations

from typing import Type

from .hosted_settings import HostedSettingsDialog, save_user_profiles

SettingsDialog: Type[HostedSettingsDialog] = HostedSettingsDialog

__all__ = ["HostedSettingsDialog", "SettingsDialog", "save_user_profiles"]

