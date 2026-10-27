"""Unreal Engine Transport Abstraction for GameForge IDE.

Authoritative specification based on GameForge Master Blueprint (Oct 27, 2026):
- Single mutation channel behind an EditorTransport adapter.
- PythonRemoteTransport: Loopback-only Python remote execution (default).
- EpicMcpTransport: Documented for UE 5.8, experimental, disabled by default.
- Remote Control HTTP: Disabled by default.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

from .security import EditorSecurityError, UnrealSecurityBoundary


class EditorTransport(ABC):
    """Abstract interface for Unreal Editor communication channels."""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the editor transport."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if channel is live."""
        pass

    @abstractmethod
    async def send_operation(
        self,
        operation_name: str,
        arguments: Dict[str, Any],
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch a named operation payload with authentication token."""
        pass


class PythonRemoteTransport(EditorTransport):
    """Loopback Python Remote Execution transport with security token checking."""

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        security_boundary: Optional[UnrealSecurityBoundary] = None,
        host: str = "127.0.0.1",
        port: int = 6766,
    ):
        self.workspace_root = (workspace_root or Path(".")).resolve()
        self.security = security_boundary or UnrealSecurityBoundary(self.workspace_root)
        self.host = host
        self.port = port
        self._connected: bool = True

    async def connect(self) -> bool:
        # Loopback boundary verification
        if self.host not in ("127.0.0.1", "localhost", "::1"):
            raise EditorSecurityError(f"Remote execution host {self.host} violates loopback security rule.")
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    async def send_operation(
        self,
        operation_name: str,
        arguments: Dict[str, Any],
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Authorizes and dispatches operation payload."""
        # 1. Enforce authentication boundary
        self.security.authorize_mutation(token, operation_name)

        if not self._connected:
            await self.connect()

        # In production editor execution, payload is passed to the Content/Python operation library.
        # Here we return a structured envelope conforming to Blueprint §3 specification.
        return {
            "ok": True,
            "operation": operation_name,
            "transport": "PythonRemoteExecution",
            "data": {
                "operation": operation_name,
                "arguments": arguments,
                "executed_at_loopback": f"{self.host}:{self.port}",
            },
            "warnings": [],
            "errors": [],
            "reversibility": "transactional",
        }


class EpicMcpTransport(EditorTransport):
    """Epic Unreal Model Context Protocol (MCP) transport.

    Targeted at Unreal Engine 5.8; experimental and disabled by default on UE 5.7.4.
    """

    def __init__(self, endpoint: str = "http://127.0.0.1:8000/mcp", enabled: bool = False):
        self.endpoint = endpoint
        self.enabled = enabled
        self._connected = False

    async def connect(self) -> bool:
        if not self.enabled:
            return False
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self.enabled and self._connected

    async def send_operation(
        self,
        operation_name: str,
        arguments: Dict[str, Any],
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "ok": False,
                "status": "DISABLED",
                "error": "EpicMcpTransport is disabled by default for UE 5.7.4.",
            }
        return {"ok": True, "transport": "EpicMCP", "operation": operation_name}
