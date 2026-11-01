"""Local Fine-tune Flywheel dataset capture (WI-9.4).

Captures accepted user interactions (designs, patches, passed compiler repairs)
into monthly JSONL datasets under <storage_root>/datasets/flywheel/<yyyymm>.jsonl.
Strictly opt-in, local-only, never transmits data off the machine.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


class FlywheelCapture:
    """Manages appending accepted interactions to flywheel datasets."""

    def __init__(self, datasets_root: Optional[Path] = None, enabled: bool = False):
        self.enabled = enabled
        if datasets_root is None:
            try:
                from ..core.settings import get_settings
                s = get_settings()
                datasets_root = s.artifacts_root.parent / "datasets"
            except Exception:
                datasets_root = Path("datasets")
        self.datasets_root = datasets_root.resolve() / "flywheel"

    def record_accepted_design(
        self,
        prompt: str,
        gds_dict: Dict[str, Any],
        workspace_id: str,
    ) -> Optional[Path]:
        """Record an accepted prompt -> final GDS interaction."""
        if not self.enabled:
            return None

        entry = {
            "type": "design_draft",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "workspace_id": workspace_id,
            "provenance": "user-accepted",
            "prompt": prompt,
            "gds": gds_dict,
        }
        return self._append_entry(entry)

    def record_accepted_patch(
        self,
        request: str,
        ops: list,
        resulting_revision: int,
        workspace_id: str,
    ) -> Optional[Path]:
        """Record an accepted change request patch."""
        if not self.enabled:
            return None

        entry = {
            "type": "gds_patch",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "workspace_id": workspace_id,
            "provenance": "user-accepted",
            "request": request,
            "ops": ops,
            "revision": resulting_revision,
        }
        return self._append_entry(entry)

    def record_compile_repair(
        self,
        diagnostics: list,
        fixed_files: Dict[str, str],
        workspace_id: str,
    ) -> Optional[Path]:
        """Record a verified C++ compilation repair."""
        if not self.enabled:
            return None

        entry = {
            "type": "cpp_repair",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "workspace_id": workspace_id,
            "provenance": "compiler-verified",
            "diagnostics": diagnostics,
            "files": fixed_files,
        }
        return self._append_entry(entry)

    def _append_entry(self, entry: Dict[str, Any]) -> Path:
        self.datasets_root.mkdir(parents=True, exist_ok=True)
        month_str = time.strftime("%Y%m")
        target_file = self.datasets_root / f"{month_str}.jsonl"
        with open(target_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return target_file
