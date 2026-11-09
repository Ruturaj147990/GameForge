"""GameForge Tool Execution Gateway package."""
from __future__ import annotations

from ...storage.approval_store import ApprovalStore
from ...storage.diff_store import DiffRecord, DiffStore
from .edit_tools import EditTools
from .game_tools import GameTools
from .gateway import ToolDefinition, ToolGateway

DiffEngine = DiffStore
GameForgeTools = GameTools

__all__ = [
    "ApprovalStore",
    "DiffEngine",
    "DiffRecord",
    "DiffStore",
    "EditTools",
    "GameForgeTools",
    "GameTools",
    "ToolDefinition",
    "ToolGateway",
]
