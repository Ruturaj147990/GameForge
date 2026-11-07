"""Context Budget & Usage Reporting Models for GameForge IDE.

Provides structured accounting of model context consumption across:
- System / developer instructions
- Conversation history
- Memory items
- Retrieved files / documents
- Tool definitions
- Other prompt overhead
- Reserved output capacity
"""

from __future__ import annotations

import time
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ContextBreakdown(BaseModel):
    """Detailed category breakdown of tokens consumed in active context."""
    system_prompt: int = Field(default=0, description="Tokens used by system and developer instructions")
    conversation: int = Field(default=0, description="Tokens used by user and assistant dialogue history")
    memory: int = Field(default=0, description="Tokens used by long-term memory and project conventions")
    retrieved_docs: int = Field(default=0, description="Tokens used by retrieved files, symbols, and search results")
    tool_definitions: int = Field(default=0, description="Tokens used by tool schemas and parameter specs")
    other_overhead: int = Field(default=0, description="Formatting tokens, JSON framing, and provider delimiters")
    reserved_output: int = Field(default=0, description="Headroom reserved for model completion output")

    def total_prompt_tokens(self) -> int:
        return (
            self.system_prompt
            + self.conversation
            + self.memory
            + self.retrieved_docs
            + self.tool_definitions
            + self.other_overhead
        )


class ContextUsageReport(BaseModel):
    """Authoritative context-usage report contract exposed to UI and telemetry."""
    model_id: str = Field(..., description="Provider or model identifier (e.g. gameforge-qwen3.5-9b)")
    nominal_capacity: int = Field(..., description="Total theoretical model context capacity in tokens")
    effective_budget: int = Field(..., description="Effective usable prompt budget before output headroom")
    used_tokens: int = Field(default=0, description="Total tokens currently consumed in prompt")
    remaining_tokens: int = Field(default=0, description="Available prompt tokens remaining before budget exhaustion")
    utilization_pct: float = Field(default=0.0, description="Context utilization percentage (0.0 to 100.0)")
    is_estimated: bool = Field(default=True, description="True if tokens are calculated via conservative estimation; False if exact from provider")
    estimation_method: str = Field(default="char_ratio", description="Exact provider measurement or estimation algorithm")
    breakdown: ContextBreakdown = Field(default_factory=ContextBreakdown, description="Categorized token breakdown")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of calculation")
    session_id: str = Field(default="", description="Active conversation session ID")

    @classmethod
    def create(
        cls,
        model_id: str,
        nominal_capacity: int,
        breakdown: ContextBreakdown,
        reserved_output: int = 2048,
        is_exact: bool = False,
        estimation_method: str = "char_ratio",
        session_id: Any = "",
    ) -> ContextUsageReport:
        effective_budget = max(512, nominal_capacity - reserved_output)
        breakdown.reserved_output = reserved_output
        used = breakdown.total_prompt_tokens()
        remaining = max(0, effective_budget - used)
        utilization = round((used / effective_budget) * 100.0, 1) if effective_budget > 0 else 100.0
        utilization = min(100.0, max(0.0, utilization))

        clean_session_id = str(session_id) if session_id is not None else ""

        return cls(
            model_id=str(model_id),
            nominal_capacity=nominal_capacity,
            effective_budget=effective_budget,
            used_tokens=used,
            remaining_tokens=remaining,
            utilization_pct=utilization,
            is_estimated=not is_exact,
            estimation_method="exact_provider" if is_exact else estimation_method,
            breakdown=breakdown,
            session_id=clean_session_id,
        )
