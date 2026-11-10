"""Forge Windows Job Object containment and child process lifecycle (AD-11, Blueprint §8.1).

Re-exports core child-process containment utilities and provides Forge-specific
process management ensuring zero orphaned subprocesses under cancellation or crash.
"""
from __future__ import annotations

from ..core.jobs import (
    ENGINE_LOCK,
    JobHandle,
    JobManager,
    adopt,
    default_job_manager,
    get_active_children,
    kill_process_tree,
    spawn,
    terminate_all_children,
)

__all__ = [
    "ENGINE_LOCK",
    "JobHandle",
    "JobManager",
    "adopt",
    "default_job_manager",
    "get_active_children",
    "kill_process_tree",
    "spawn",
    "terminate_all_children",
]
