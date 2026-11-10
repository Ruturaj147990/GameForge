"""GameForge Engine Adapters and Discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

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


def get_engine_adapter(
    engine_name: str, engine_discovery: Optional[EngineDiscoveryResult] = None
) -> EngineAdapter:
    """Factory function returning the appropriate EngineAdapter instance."""
    normalized = engine_name.lower().strip()
    if normalized in ("unreal", "ue", "unreal_engine", "ue5"):
        return UnrealEngineAdapter(engine_discovery=engine_discovery)
    elif normalized in ("unity", "unity_engine"):
        return UnityEngineAdapter(engine_discovery=engine_discovery)
    raise ValueError(f"Unsupported engine adapter: '{engine_name}'. Supported engines: unreal, unity.")


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
    "get_engine_adapter",
    "discover_unreal_engine",
    "discover_unity_engine",
    "discover_toolchains",
    "discover_environment",
]

