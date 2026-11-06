"""Task Approach Modes, Autonomy Profiles, and Lifecycle State Machine for GameForge 1.0.

Authoritative specification conforming to GameForge 1.0 Master Transformation Directive:
- Two independent user-selectable controls: Task Approach and Autonomy Profile.
- Task Approach: Planning vs Fast.
- Autonomy Profile: Manual vs Auto-Edit vs Agentic.
- Authoritative execution state machine for all tasks.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal


class TaskMode(str, Enum):
    """Independent user control defining how tasks are approached."""
    PLANNING = "planning"  # Generate actionable plan in chat, allow revision, await Proceed
    FAST = "fast"          # Skip formal chat plan review; begin execution immediately

    def __str__(self) -> str:
        return str(self.value)


class AutonomyProfile(str, Enum):
    """Independent user control defining permission boundaries for execution."""
    MANUAL = "manual"        # Read-only automatically; ask before all file edits, commands, builds
    AUTO_EDIT = "auto_edit"  # Auto-inspect and auto-edit project files; ask before commands, builds, external ops
    AGENTIC = "agentic"      # Auto safe edits, allowlisted project commands, builds, tests, Unreal ops; ask only for high-risk/destructive

    def __str__(self) -> str:
        return str(self.value)


class TaskLifecycleStatus(str, Enum):
    """Authoritative task execution state machine states."""
    CREATED = "CREATED"
    UNDERSTANDING = "UNDERSTANDING"
    INVESTIGATING = "INVESTIGATING"
    PLANNING = "PLANNING"
    AWAITING_PLAN_APPROVAL = "AWAITING_PLAN_APPROVAL"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_TOOL = "WAITING_TOOL"
    AWAITING_PERMISSION = "AWAITING_PERMISSION"
    REPAIRING = "REPAIRING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"

    def __str__(self) -> str:
        return str(self.value)

    def is_terminal(self) -> bool:
        return self in (
            TaskLifecycleStatus.COMPLETED,
            TaskLifecycleStatus.FAILED,
            TaskLifecycleStatus.BLOCKED,
            TaskLifecycleStatus.CANCELLED,
        )

    def is_active(self) -> bool:
        return not self.is_terminal()


# Valid state machine transitions
VALID_TRANSITIONS: dict[TaskLifecycleStatus, set[TaskLifecycleStatus]] = {
    TaskLifecycleStatus.CREATED: {
        TaskLifecycleStatus.UNDERSTANDING,
        TaskLifecycleStatus.CANCELLED,
        TaskLifecycleStatus.FAILED,
    },
    TaskLifecycleStatus.UNDERSTANDING: {
        TaskLifecycleStatus.INVESTIGATING,
        TaskLifecycleStatus.PLANNING,
        TaskLifecycleStatus.RUNNING,
        TaskLifecycleStatus.COMPLETED,  # e.g. purely informational query
        TaskLifecycleStatus.FAILED,
        TaskLifecycleStatus.CANCELLED,
    },
    TaskLifecycleStatus.INVESTIGATING: {
        TaskLifecycleStatus.PLANNING,
        TaskLifecycleStatus.RUNNING,
        TaskLifecycleStatus.WAITING_TOOL,
        TaskLifecycleStatus.FAILED,
        TaskLifecycleStatus.CANCELLED,
    },
    TaskLifecycleStatus.PLANNING: {
        TaskLifecycleStatus.AWAITING_PLAN_APPROVAL,
        TaskLifecycleStatus.RUNNING,  # in Fast mode
        TaskLifecycleStatus.INVESTIGATING,
        TaskLifecycleStatus.FAILED,
        TaskLifecycleStatus.CANCELLED,
    },
    TaskLifecycleStatus.AWAITING_PLAN_APPROVAL: {
        TaskLifecycleStatus.PLANNING,  # user sent revision prompt
        TaskLifecycleStatus.QUEUED,
        TaskLifecycleStatus.RUNNING,   # user confirmed Proceed
        TaskLifecycleStatus.CANCELLED,
    },
    TaskLifecycleStatus.QUEUED: {
        TaskLifecycleStatus.RUNNING,
        TaskLifecycleStatus.CANCELLED,
    },
    TaskLifecycleStatus.RUNNING: {
        TaskLifecycleStatus.WAITING_TOOL,
        TaskLifecycleStatus.AWAITING_PERMISSION,
        TaskLifecycleStatus.REPAIRING,
        TaskLifecycleStatus.VERIFYING,
        TaskLifecycleStatus.COMPLETED,
        TaskLifecycleStatus.FAILED,
        TaskLifecycleStatus.BLOCKED,
        TaskLifecycleStatus.CANCELLED,
    },
    TaskLifecycleStatus.WAITING_TOOL: {
        TaskLifecycleStatus.RUNNING,
        TaskLifecycleStatus.AWAITING_PERMISSION,
        TaskLifecycleStatus.REPAIRING,
        TaskLifecycleStatus.VERIFYING,
        TaskLifecycleStatus.FAILED,
        TaskLifecycleStatus.BLOCKED,
        TaskLifecycleStatus.CANCELLED,
    },
    TaskLifecycleStatus.AWAITING_PERMISSION: {
        TaskLifecycleStatus.RUNNING,  # approved
        TaskLifecycleStatus.CANCELLED,
        TaskLifecycleStatus.BLOCKED,  # rejected
    },
    TaskLifecycleStatus.REPAIRING: {
        TaskLifecycleStatus.RUNNING,
        TaskLifecycleStatus.VERIFYING,
        TaskLifecycleStatus.FAILED,
        TaskLifecycleStatus.BLOCKED,  # retry limit reached
        TaskLifecycleStatus.CANCELLED,
    },
    TaskLifecycleStatus.VERIFYING: {
        TaskLifecycleStatus.COMPLETED,
        TaskLifecycleStatus.REPAIRING,  # verification failed
        TaskLifecycleStatus.RUNNING,
        TaskLifecycleStatus.FAILED,
        TaskLifecycleStatus.CANCELLED,
    },
    # Terminal states have no outbound transitions
    TaskLifecycleStatus.COMPLETED: set(),
    TaskLifecycleStatus.FAILED: set(),
    TaskLifecycleStatus.BLOCKED: {TaskLifecycleStatus.RUNNING},  # may be unblocked/resumed
    TaskLifecycleStatus.CANCELLED: set(),
}


def can_transition(source: TaskLifecycleStatus, target: TaskLifecycleStatus) -> bool:
    """Checks whether transition from source to target is legal."""
    allowed = VALID_TRANSITIONS.get(source, set())
    return target in allowed
