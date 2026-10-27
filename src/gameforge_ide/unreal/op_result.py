"""Structured result envelope shared by real and test editor-operation backends."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OperationResult(BaseModel):
    ok: bool
    operation: str
    data: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    affected_paths: List[str] = Field(default_factory=list)
    reversibility: str = "transactional"  # "transactional", "snapshot-only", "read-only"
    snapshot_id: Optional[str] = None
