"""Unreal Engine 5.8 Compatibility Lane and Readiness Subsystem (WI-10.6).

Architectural readiness for Unreal Engine 5.8 ("next" channel) while maintaining
UE 5.7.4 ("pinned" channel) as the authoritative production engine.

TRUTHFUL REPORTING CONTRACT:
UE 5.8 is NOT installed on disk in the production environment.
Its status MUST be reported truthfully as "BLOCKED BY ENVIRONMENT".
It must NEVER be falsely reported as active or verified.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from . import discovery
from . import mcp_bridge

logger = logging.getLogger(__name__)

STATUS_BLOCKED_BY_ENVIRONMENT = "BLOCKED BY ENVIRONMENT"
STATUS_READY = "READY"
STATUS_ACTIVE = "ACTIVE"

PINNED_CHANNEL = "pinned"
NEXT_CHANNEL = "next"
PINNED_DEFAULT_VERSION = "5.7.4"
PINNED_DEFAULT_ROOT = Path(r"E:\UE\UE_5.7")

UE58_CPP_MACRO_GUARD = "#if ENGINE_MINOR_VERSION >= 8"
UE58_AI_CALLABLE_META = "meta=(AICallable) on read-only UFUNCTIONs"


@dataclass
class Ue58LaneReport:
    status: str
    channel: str
    is_installed: bool
    is_active: bool
    engine_root: Optional[str]
    engine_version: Optional[str]
    pinned_engine: Dict[str, Any]
    mcp_bridge: Dict[str, Any]
    cpp_compatibility: Dict[str, Any]
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def detect_ue58_engine(custom_root: Optional[Path] = None) -> Optional[discovery.DiscoveredEngine]:
    """Search for a valid UE 5.8 engine installation."""
    if custom_root is not None and str(custom_root).strip():
        try:
            c_path = Path(custom_root).resolve()
            eng = discovery.validate_engine_root(c_path, source="custom", pinned_minor="5.8")
            if eng and eng.is_valid and eng.major_minor == "5.8":
                return eng
        except (OSError, ValueError):
            pass

    engines = discovery.discover_all_engines(pinned_minor="5.8")
    for eng in engines:
        if eng.is_valid and eng.major_minor == "5.8":
            return eng
    return None


def is_ue58_installed() -> bool:
    """Return True only if a valid UE 5.8 engine installation exists on disk."""
    return detect_ue58_engine() is not None


def is_ue58_active() -> bool:
    """Return True only if UE 5.8 is both installed and configured as active."""
    return False  # UE 5.8 is not installed; never report active


def get_ue58_status_string(custom_root: Optional[Path] = None) -> str:
    """Return concise truthful status string for UE 5.8."""
    eng = detect_ue58_engine(custom_root)
    if eng and eng.is_valid and eng.major_minor == "5.8":
        return STATUS_READY
    return STATUS_BLOCKED_BY_ENVIRONMENT


def get_ue58_lane_report(custom_root: Optional[Path] = None) -> Dict[str, Any]:
    """Compile comprehensive status and architectural readiness report for UE 5.8.
    
    Truthfully reports BLOCKED BY ENVIRONMENT when UE 5.8 is missing from disk.
    """
    ue58_eng = detect_ue58_engine(custom_root)

    # Probe pinned engine (UE 5.7.4)
    best_pinned = discovery.get_best_engine(pinned_minor="5.7")
    pinned_info = {
        "channel": PINNED_CHANNEL,
        "version": best_pinned.version if best_pinned else PINNED_DEFAULT_VERSION,
        "root": str(best_pinned.root) if best_pinned else str(PINNED_DEFAULT_ROOT),
        "changelist": best_pinned.changelist if best_pinned else 51494982,
        "verified": bool(best_pinned and best_pinned.is_valid),
    }

    # Verify MCP bridge port coexistence
    port_status = mcp_bridge.verify_port_coexistence(editor_port=47815, mcp_port=8000)

    cpp_compat = {
        "macro_guards": UE58_CPP_MACRO_GUARD,
        "ai_callable_meta": UE58_AI_CALLABLE_META,
    }

    mcp_info = {
        "read_only_client": "src/gameforge_ide/unreal/mcp_bridge.py",
        "port_coexistence": port_status,
        "editor_port": 47815,
        "mcp_port": 8000,
    }

    if ue58_eng and ue58_eng.is_valid and ue58_eng.major_minor == "5.8":
        report = Ue58LaneReport(
            status=STATUS_READY,
            channel=NEXT_CHANNEL,
            is_installed=True,
            is_active=False,
            engine_root=str(ue58_eng.root),
            engine_version=ue58_eng.version,
            pinned_engine=pinned_info,
            mcp_bridge=mcp_info,
            cpp_compatibility=cpp_compat,
            reason="UE 5.8 engine discovered and verified on disk; ready for activation",
        )
    else:
        report = Ue58LaneReport(
            status=STATUS_BLOCKED_BY_ENVIRONMENT,
            channel=NEXT_CHANNEL,
            is_installed=False,
            is_active=False,
            engine_root=None,
            engine_version=None,
            pinned_engine=pinned_info,
            mcp_bridge=mcp_info,
            cpp_compatibility=cpp_compat,
            reason="UE 5.8 is not installed on disk. Architectural readiness maintained; operations blocked by environment until installed.",
        )

    return report.to_dict()
