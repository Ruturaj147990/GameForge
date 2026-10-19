"""GameForge Engine Adapters and Discovery."""

from .base import (
    AssetValidationResult,
    BuildResult,
    EngineAdapter,
    EngineDiscoveryResult,
    ProbeMeasurement,
    SubprocessResult,
    TestResult,
    safe_subprocess_run,
)
from .discovery import (
    discover_environment,
    discover_toolchains,
    discover_unity_engine,
    discover_unreal_engine,
)
from .unity import UnityEngineAdapter
from .unreal import UnrealEngineAdapter

__all__ = [
    "EngineAdapter",
    "EngineDiscoveryResult",
    "BuildResult",
    "TestResult",
    "ProbeMeasurement",
    "AssetValidationResult",
    "SubprocessResult",
    "safe_subprocess_run",
    "UnrealEngineAdapter",
    "UnityEngineAdapter",
    "discover_unreal_engine",
    "discover_unity_engine",
    "discover_toolchains",
    "discover_environment",
]
