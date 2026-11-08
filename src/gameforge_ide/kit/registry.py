"""Kit module registry and parameter models (spec §3.2, WI-5.14).

Registers kit runtime modules and their parameter schemas, property maps,
and dependency metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple, Type
from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True)
class KitModule:
    """Metadata and bindings for a C++ kit actor/component."""

    module_id: str
    version: str
    runtime_class: str
    entity_kinds: FrozenSet[str]
    params_model: Type[BaseModel]
    property_map: Dict[str, str]
    required_plugins: Tuple[str, ...] = ("GameForge",)
    game_module_deps: Tuple[str, ...] = ("GameForgeRuntime",)
    emits: Tuple[str, ...] = ()
    automation_tests: Tuple[str, ...] = ()
    status: str = "PASS"
    evidence: Tuple[str, ...] = ("reports/P5/kit_scenarios_final.json",)
    features: Tuple[str, ...] = ()


KIT: Dict[str, KitModule] = {}


def register(m: KitModule) -> KitModule:
    """Register a kit module into the central dictionary."""
    KIT[m.module_id] = m
    return m


def get_module(module_id: str) -> KitModule:
    """Retrieve registered kit module or raise KeyError."""
    if module_id not in KIT:
        # Trigger lazy load of modules if empty
        _ensure_modules_loaded()
    if module_id not in KIT:
        raise KeyError(f"Kit module {module_id!r} not found in registry; known: {sorted(KIT.keys())}")
    return KIT[module_id]


def all_modules() -> List[KitModule]:
    _ensure_modules_loaded()
    return list(KIT.values())


def _ensure_modules_loaded() -> None:
    if not KIT:
        from . import modules  # noqa: F401
