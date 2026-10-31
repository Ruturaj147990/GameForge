"""Forge Handlers Registry and Handler Contract.

Handler Contract (AD-11):
1. Idempotent: a handler may be re-run after a crash, so it must not fail just because its output already exists.
2. Cancellable: poll ctx.cancel at least every 2 s in loops, and pass it to the toolchain (toolchain.cancel_event).
3. Fail closed: return StepOutcome(False, ...). Never raise for expected failures.
4. Evidence: artifacts are paths inside the project's Saved/GameForge/evidence/ or the run dir.
5. Use blocked=True for environment problems (engine missing, VRAM scheduler refusal, approval revoked).
"""
from __future__ import annotations

from typing import Dict
from ..executor import Handler

HANDLERS: Dict[str, Handler] = {}


def register_handler(kind: str, handler: Handler) -> None:
    HANDLERS[kind] = handler
