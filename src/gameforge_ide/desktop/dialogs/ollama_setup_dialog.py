"""Alias module redirecting ollama_setup_dialog to ollama_setup."""
from __future__ import annotations

from .ollama_setup import (
    OllamaSetupDialog,
    check_ollama_status,
    find_ollama_executable,
    get_ollama_models_directory,
    start_ollama_service,
)

__all__ = [
    "OllamaSetupDialog",
    "check_ollama_status",
    "find_ollama_executable",
    "get_ollama_models_directory",
    "start_ollama_service",
]
