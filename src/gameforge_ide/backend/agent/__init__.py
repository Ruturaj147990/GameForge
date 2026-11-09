"""GameForge Agent Runtime package.

Exposes the bounded agent loop, context manager, intent classifier, plan generator,
repair engine, task state, and canonical tool-call parser.
"""

from .context_manager import ContextManager
from .intent_classifier import IntentClassification, classify_intent
from .plan_generator import PlanGenerator
from .repair_system import FailureCategory, RepairEngine, RootCause
from .runtime import AgentEvent, AgentRuntime
from .task_plan import PlanValidationError, TaskNode, TaskPlan
from .task_state import (
    LedgerEntry,
    PendingApproval,
    TaskAcceptancePredicate,
    TaskBudget,
    TaskState,
)
from .tool_call_parser import (
    DEFAULT_ALIASES,
    DEFAULT_KNOWN_TOOLS,
    ParsedToolCall,
    ParserResult,
    StreamingToolGuard,
    parse_text_for_tool_calls,
)

__all__ = [
    "AgentEvent",
    "AgentRuntime",
    "ContextManager",
    "DEFAULT_ALIASES",
    "DEFAULT_KNOWN_TOOLS",
    "FailureCategory",
    "IntentClassification",
    "LedgerEntry",
    "ParsedToolCall",
    "ParserResult",
    "PendingApproval",
    "PlanGenerator",
    "PlanValidationError",
    "RepairEngine",
    "RootCause",
    "StreamingToolGuard",
    "TaskAcceptancePredicate",
    "TaskBudget",
    "TaskNode",
    "TaskPlan",
    "TaskState",
    "classify_intent",
    "parse_text_for_tool_calls",
]
