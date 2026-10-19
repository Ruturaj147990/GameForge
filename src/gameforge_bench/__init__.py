"""GameForge Benchmark Foundation (gameforge_bench)

A reproducible, cross-engine benchmark orchestration and evaluation framework.
"""

__version__ = "0.1.0"
__benchmark_version__ = "v0.1"

from .grading import GradingLayer, RunStatus
from .task_loader import LogicalTask, TaskSpec, load_task, load_task_inventory
from .task_validation import validate_all_specs

__all__ = [
    "GradingLayer",
    "RunStatus",
    "TaskSpec",
    "LogicalTask",
    "load_task",
    "load_task_inventory",
    "validate_all_specs",
    "__version__",
    "__benchmark_version__",
]
