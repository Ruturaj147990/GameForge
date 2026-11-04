"""Alias module redirecting settings_dialog to hosted_settings."""
from __future__ import annotations

from .hosted_settings import HostedSettingsDialog, save_user_profiles

SettingsDialog = HostedSettingsDialog

__all__ = ["HostedSettingsDialog", "SettingsDialog", "save_user_profiles"]
