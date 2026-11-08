"""Command Execution Contract and Data Models for GameForge IDE.

Authoritative schemas for command execution requests, safety classification,
and results governed by the Central Command Execution Broker.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from .modes import PermissionsMode


class CommandStatus(str, Enum):
    """Lifecycle states of an orchestrated command execution."""
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"

    def __str__(self) -> str:
        return str(self.value)


class RiskCategory(str, Enum):
    """Classification of command risk and side-effect severity."""
    ROUTINE_READ = "routine_read"            # cat, dir, git status, git log, pwd, ls
    DEVELOPMENT_TEST = "development_test"    # pytest, python script, test runners, typecheck
    PROJECT_BUILD = "project_build"          # UBT, UAT, cmake, dotnet, msbuild
    WORKSPACE_EDIT = "workspace_edit"        # project-local file generation, script modification
    DESTRUCTIVE_DELETE = "destructive_delete"# recursive remove, broad unlinking
    SYSTEM_MODIFICATION = "system_modification" # registry, system-wide variables, services
    ELEVATED_ADMIN = "elevated_admin"        # requires administrator privileges
    OUTSIDE_WORKSPACE = "outside_workspace"  # accesses filesystem paths outside workspace root
    UNCERTAIN_SCRIPT = "uncertain_script"    # unparsable or ambiguous script invocation


class CommandExecutionRequest(BaseModel):
    """Request payload sent to CommandExecutionBroker."""
    command: str = Field(..., description="Raw command line string")
    shell: str = Field(default="direct", description="Target shell: direct (default shell-free), powershell, cmd, or bash")
    working_directory: str = Field(default="", description="Working directory path")
    permissions_mode: PermissionsMode = Field(default=PermissionsMode.AUTO, description="Active permissions mode")
    reason: str = Field(default="", description="Engineering intent/purpose for executing this command")
    agent_id: str = Field(default="agent_main", description="Logical agent requesting execution")
    turn_id: Optional[str] = Field(default=None, description="Active dialogue turn ID")
    execution_id: str = Field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:8]}")
    timeout_seconds: int = Field(default=120, description="Process execution timeout limit")
    env_overrides: Dict[str, str] = Field(default_factory=dict, description="Custom environment variable overrides")


class CommandExecutionResult(BaseModel):
    """Complete, verifiable result returned by CommandExecutionBroker."""
    execution_id: str
    command: str
    shell: str
    working_directory: str
    status: CommandStatus
    permissions_mode: PermissionsMode
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    risk_category: RiskCategory = RiskCategory.ROUTINE_READ
    requires_approval: bool = False
    approved_by_user: Optional[bool] = None
    error_message: Optional[str] = None
    started_at: float = Field(default_factory=time.time)
    finished_at: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
