"""GameForge IDE — Desktop In-Process Services Package.

Provides high-performance in-process service adapters connecting UI panels directly
to Agent, Tools, Forge build pipeline, Systems diagnostics, and Projects registry.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ActionRunner",
    "AgentService",
    "ForgeService",
    "PlanRunner",
    "ProjectsService",
    "SystemsService",
    "ToolService",
]


def __getattr__(name: str) -> Any:
    if name == "ActionRunner":
        from .action_runner import ActionRunner
        return ActionRunner
    if name == "AgentService":
        from .agent_service import AgentService
        return AgentService
    if name == "ForgeService":
        from .forge_service import ForgeService
        return ForgeService
    if name == "PlanRunner":
        from .plan_runner import PlanRunner
        return PlanRunner
    if name == "ProjectsService":
        from .projects_service import ProjectsService
        return ProjectsService
    if name == "SystemsService":
        from .systems_service import SystemsService
        return SystemsService
    if name == "ToolService":
        from .tool_service import ToolService
        return ToolService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

