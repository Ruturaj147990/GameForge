"""GameForge IDE Backend package.

Exposes the bounded agent runtime, model providers, session manager, security boundaries,
and tool execution gateway.
"""

from .agent.runtime import AgentEvent, AgentRuntime
from .providers.router import ModelRouter
from .session_manager import Session, SessionManager
from .tools.gateway import ToolGateway

__all__ = [
    "AgentEvent",
    "AgentRuntime",
    "ModelRouter",
    "Session",
    "SessionManager",
    "ToolGateway",
]
