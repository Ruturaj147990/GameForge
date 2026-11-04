"""RunStore: persistence, event logging and runs index for Forge runs (AD-11).

Delegates to authoritative storage subsystem in src/gameforge_ide/storage/forge_store.py.
"""
from __future__ import annotations

from ..storage.forge_store import ForgeStore, RunStore, _INDEX_LOCK

__all__ = ["ForgeStore", "RunStore", "_INDEX_LOCK"]

