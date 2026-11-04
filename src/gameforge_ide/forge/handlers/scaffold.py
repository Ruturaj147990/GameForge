"""Forge step handler for project scaffolding (AD-11)."""
from __future__ import annotations

from ..executor import StepContext, StepOutcome
from .legacy_stages import legacy_scaffold


def scaffold_handler(ctx: StepContext) -> StepOutcome:
    """Scaffold a new Unreal C++ project with GameForge configuration and plugin."""
    return legacy_scaffold(ctx)


__all__ = ["scaffold_handler", "legacy_scaffold"]
