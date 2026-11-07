"""Backend Agent Service for GameForge IDE.

Authoritative backend service providing headless context-usage telemetry,
session orchestration, and agent query endpoints.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..agent.context_manager import ContextManager
from ..agent.runtime import AgentRuntime
from ..models.context_usage import ContextUsageReport
from ..session_manager import SessionManager

logger = logging.getLogger(__name__)


class BackendAgentService:
    """Headless backend service providing agent runtime management and telemetry."""

    def __init__(self, workspace_root: Union[str, Path]) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.session_manager = SessionManager(self.workspace_root)
        self.runtime = AgentRuntime(self.workspace_root, session_manager=self.session_manager)
        self.context_manager = self.runtime.context_manager

    def get_context_usage(
        self,
        session_id: str,
        model_id: Optional[str] = None,
    ) -> ContextUsageReport:
        """Query live context usage report for a given session and model."""
        return self.runtime.get_context_usage(session_id=session_id, model_id=model_id)

    def create_session(self, **kwargs: Any) -> Any:
        return self.session_manager.create_session(**kwargs)

    def get_session(self, session_id: str) -> Any:
        return self.session_manager.get_session(session_id)


# Expose alias
AgentService = BackendAgentService
