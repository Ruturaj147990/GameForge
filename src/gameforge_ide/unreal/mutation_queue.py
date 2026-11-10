"""Serialized Mutation Queue and Readiness Gate for GameForge Unreal Engine Integration.

Authoritative specification based on GameForge Master Blueprint (Oct 27, 2026):
- Rule 6: One writer at a time — strict serial execution queue.
- Idle gate: Mutations wait until level is loaded, shaders finished, not in PIE.
- Bound every operation: Per-call timeouts and typed crash/hang detection.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, Optional
from pydantic import BaseModel


class EditorReadinessState(BaseModel):
    is_ready: bool = True
    compiling_shaders: bool = False
    in_pie: bool = False
    level_loading: bool = False
    reason: Optional[str] = None


class SerializedMutationQueue:
    """Ensures serialized execution of mutations on Unreal's game/editor thread."""

    def __init__(self, default_timeout_seconds: float = 30.0):
        if default_timeout_seconds <= 0:
            raise ValueError(f"default_timeout_seconds must be > 0 (got {default_timeout_seconds})")
        self._lock = asyncio.Lock()
        self.default_timeout = default_timeout_seconds
        self._readiness = EditorReadinessState()
        self._last_execution_time: float = 0.0

    def set_readiness(
        self,
        compiling_shaders: bool = False,
        in_pie: bool = False,
        level_loading: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        """Updates editor readiness status from telemetry."""
        is_ready = not (compiling_shaders or in_pie or level_loading)
        if not is_ready and not reason:
            if compiling_shaders:
                reason = "Editor busy compiling shaders."
            elif in_pie:
                reason = "Play-In-Editor (PIE) session active."
            elif level_loading:
                reason = "Editor loading level."
        self._readiness = EditorReadinessState(
            is_ready=is_ready,
            compiling_shaders=compiling_shaders,
            in_pie=in_pie,
            level_loading=level_loading,
            reason=reason,
        )

    def get_readiness(self) -> EditorReadinessState:
        return self._readiness

    async def execute_mutation(
        self,
        operation_name: str,
        coro_func: Callable[[], Awaitable[Dict[str, Any]]],
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Acquires the exclusive serial mutation lock, validates readiness, and executes within timeout."""
        timeout = self.default_timeout if timeout_seconds is None else timeout_seconds
        if timeout <= 0:
            return {
                "ok": False,
                "status": "ERROR",
                "error": f"Invalid timeout {timeout} for operation '{operation_name}'; must be > 0.",
                "operation": operation_name,
            }

        # 1. Acquire serial lock
        async with self._lock:
            # 2. Check idle readiness gate
            if not self._readiness.is_ready:
                return {
                    "ok": False,
                    "status": "BUSY",
                    "error": f"Editor not ready for mutation: {self._readiness.reason}",
                    "operation": operation_name,
                }

            # 3. Bounded execution
            t0 = time.monotonic()
            try:
                result = await asyncio.wait_for(coro_func(), timeout=timeout)
                self._last_execution_time = time.monotonic() - t0
                return result
            except asyncio.TimeoutError:
                return {
                    "ok": False,
                    "status": "TIMEOUT",
                    "error": f"Editor operation '{operation_name}' timed out after {timeout} seconds.",
                    "operation": operation_name,
                }
            except Exception as e:
                return {
                    "ok": False,
                    "status": "ERROR",
                    "error": f"Exception executing editor operation '{operation_name}': {e}",
                    "operation": operation_name,
                }
