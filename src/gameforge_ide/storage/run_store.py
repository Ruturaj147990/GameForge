"""Authoritative RunStore module for GameForge IDE.

Re-exports RunStore from forge_store for storage subsystem consistency.
"""
from __future__ import annotations

from .forge_store import ForgeStore, RunStore

__all__ = ["ForgeStore", "RunStore"]
