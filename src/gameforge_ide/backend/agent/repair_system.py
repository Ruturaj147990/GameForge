"""Automatic Error Repair and Pipeline Stage Recovery Engine for GameForge 1.0.

Conforms to GameForge 1.0 Master Transformation Directive:
- Section 2.9 & Section 8.3-8.5: First-class automatic error detection, diagnosis, and repair.
- Policy:
  * Up to 5 meaningful attempts per distinct root cause.
  * Stop after 2 consecutive attempts without measurable progress (identical diff or repeated errors).
  * Invalidate affected downstream stages.
  * Resume from earliest affected stage.
  * Preserve valid outputs and checkpoints.
  * Never weaken tests to obtain success.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from .code_verify import MSVC_DIAG_RE as _SHARED_MSVC_DIAG_RE, _extract_symbol, parse_diagnostics

logger = logging.getLogger(__name__)

# Expanded MSVC / Linker (LNK\d+) / UHT diagnostic regex
MSVC_DIAG_RE = re.compile(
    r"^(?:(?P<file>(?:[a-zA-Z]:[\\/])?[^\(\r\n:]+?)(?:\((?P<line>\d+)(?:,\s*(?P<col>\d+))?\))?\s*:\s*)?"
    r"(?P<severity>fatal error|error|warning|Error|Warning)\s*"
    r"(?P<code>(?:[A-Z]+\d+|LNK\d+|C\d+|UHT\d+))?\s*:\s*(?P<message>.+)$"
)


class FailureCategory(str, Enum):
    """Categorized root causes of build, test, pipeline, or compiler failures."""
    CODE_DEFECT = "code_defect"                  # Syntax, type, linker, UHT, or compiler errors
    LOGIC_DEFECT = "logic_defect"                # Assertion failure, scenario logic, math error
    CONTENT_DEFECT = "content_defect"            # Asset missing, invalid material, texture format
    CONFIG_DEFECT = "config_defect"              # .ini settings, target rules, map settings
    SCENARIO_FAILURE = "scenario_failure"        # Playtest goal not met, timeout, navigation stuck
    ENVIRONMENT_FAILURE = "environment_failure"  # Missing SDK, disk space, port conflict
    DEPENDENCY_FAILURE = "dependency_failure"    # Missing module, unbuilt dependency
    UNKNOWN = "unknown"


class DiagnosticRecord(BaseModel):
    """Parsed structured diagnostic from compiler, test runner, or engine log."""
    file: str = ""
    line: int = 0
    column: int = 0
    code: str = ""
    message: str
    severity: str = "error"  # error, warning, note
    symbol: Optional[str] = None
    stage_id: Optional[str] = None


class RootCause(BaseModel):
    """Identified distinct root cause of a failure."""
    cause_id: str
    category: FailureCategory
    signature: str          # Normalized key (file + error type + symbol)
    description: str
    primary_file: Optional[str] = None
    diagnostics: List[DiagnosticRecord] = Field(default_factory=list)


class RepairAttempt(BaseModel):
    """Record of a single attempt to repair a root cause."""
    attempt_number: int
    cause_signature: str
    proposed_diff: str
    diff_hash: str
    modified_files: List[str] = Field(default_factory=list)
    result_status: str  # "SUCCESS", "FAILED", "NOOP", "BLOCKED"
    diagnostic_count_before: int = 0
    diagnostic_count_after: int = 0
    timestamp: float = Field(default_factory=time.time)


class RepairEngine:
    """Manages automatic detection, diagnosis, and bounded repair of engineering defects."""

    MAX_ATTEMPTS_PER_CAUSE = 5
    MAX_CONSECUTIVE_NO_PROGRESS = 2

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root).resolve()
        # Track attempts keyed by cause_signature: List[RepairAttempt]
        self._history_by_cause: Dict[str, List[RepairAttempt]] = {}
        # Track seen diff hashes per cause to prevent repeated cyclic edits
        self._diff_hashes_by_cause: Dict[str, Set[str]] = {}

    @property
    def attempt_counts(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self._history_by_cause.items()}

    def parse_diagnostics(self, raw_output: Any) -> List[DiagnosticRecord]:
        """Parse compiler, linker (LNK), and UHT diagnostics using MSVC_DIAG_RE and parse_diagnostics."""
        records: List[DiagnosticRecord] = []
        if isinstance(raw_output, str):
            for line in raw_output.splitlines():
                sline = line.strip()
                if not sline:
                    continue
                m = MSVC_DIAG_RE.match(sline)
                if m:
                    raw_file = (m.group("file") or "").strip().replace("\\", "/")
                    if raw_file.upper() == "LINK":
                        raw_file = ""
                    elif raw_file.endswith(".cpp.obj") or raw_file.endswith(".c.obj"):
                        raw_file = raw_file[:-4]
                    code = (m.group("code") or "").strip()
                    msg = m.group("message").strip()
                    sym = _extract_symbol(msg)
                    records.append(
                        DiagnosticRecord(
                            file=raw_file,
                            line=int(m.group("line") or 0),
                            column=int(m.group("col") or 0),
                            code=code,
                            message=f"{code}: {msg}" if code and code not in msg else msg,
                            severity=m.group("severity").lower(),
                            symbol=sym,
                        )
                    )
        if not records:
            for d in parse_diagnostics(raw_output):
                records.append(
                    DiagnosticRecord(
                        file=d.get("file", ""),
                        line=int(d.get("line", 0) or 0),
                        column=int(d.get("column", 0) or 0),
                        code=str(d.get("code", "") or ""),
                        message=d.get("message", ""),
                        severity=d.get("severity", "error"),
                        symbol=d.get("symbol"),
                    )
                )
        return records

    def extract_root_cause(
        self,
        raw_output: Any,
        stage_id: Optional[str] = None,
        context_files: Optional[List[str]] = None,
    ) -> RootCause:
        """Parses output/logs and classifies the primary root cause."""
        diagnostics_data = parse_diagnostics(raw_output)
        diags = [
            DiagnosticRecord(
                file=d.get("file", ""),
                line=int(d.get("line", 0) or 0),
                column=int(d.get("column", 0) or 0),
                code=str(d.get("code", "") or ""),
                message=d.get("message", ""),
                severity=d.get("severity", "error"),
                symbol=d.get("symbol"),
                stage_id=stage_id,
            )
            for d in diagnostics_data
        ]
        if not diags and isinstance(raw_output, str):
            diags = self.parse_diagnostics(raw_output)
            for d in diags:
                d.stage_id = stage_id

        text = raw_output if isinstance(raw_output, str) else json.dumps(raw_output, default=str)

        # 1. Check for scenario execution failures (e.g. stage 9 Scenarios)
        if stage_id in ("scenarios", "qa", "playtest") or "Step " in text and "failed:" in text or "SCENARIO" in text:
            m_scen = re.search(r"Step\s+\d+\s*\(([^)]+)\)\s*failed:\s*([^\r\n]+)", text)
            desc = m_scen.group(0) if m_scen else "Scenario execution assertion failed."
            sig = f"scenario:{stage_id}:{hashlib.sha256(desc.encode()).hexdigest()[:8]}"
            return RootCause(
                cause_id=f"rc_{uuid_hex(sig)}",
                category=FailureCategory.SCENARIO_FAILURE,
                signature=sig,
                description=desc,
                primary_file=diags[0].file if diags else None,
                diagnostics=diags,
            )

        # 2. Check for config / UBT rules defects
        if any(k in text for k in ("Couldn't find target rules", "DefaultEngine.ini", "DefaultGame.ini", "Target.cs", ".ini")):
            sig = f"config:{stage_id}:{hashlib.sha256(text[:100].encode()).hexdigest()[:8]}"
            return RootCause(
                cause_id=f"rc_{uuid_hex(sig)}",
                category=FailureCategory.CONFIG_DEFECT,
                signature=sig,
                description="Engine or build configuration rules defect.",
                primary_file=diags[0].file if diags else None,
                diagnostics=diags,
            )

        # 3. Check for compiler / linker / UHT defects
        if diags:
            first = diags[0]
            norm_file = Path(first.file).name if first.file else "unknown"
            sym = first.symbol or first.code or "unknown_symbol"
            sig = f"code:{norm_file}:{first.line}:{sym}"
            return RootCause(
                cause_id=f"rc_{uuid_hex(sig)}",
                category=FailureCategory.CODE_DEFECT,
                signature=sig,
                description=first.message[:200],
                primary_file=first.file or None,
                diagnostics=diags,
            )

        # 4. Fallback unknown
        sig = f"unknown:{stage_id}:{hashlib.sha256(text[:100].encode()).hexdigest()[:8]}"
        return RootCause(
            cause_id=f"rc_{uuid_hex(sig)}",
            category=FailureCategory.UNKNOWN,
            signature=sig,
            description="Unclassified stage failure.",
            primary_file=None,
            diagnostics=diags,
        )

    def can_attempt_repair(self, cause: RootCause) -> Tuple[bool, str]:
        """Checks policy limits: max 5 attempts, max 2 consecutive with no progress."""
        history = self._history_by_cause.get(cause.signature, [])
        attempt_count = len(history)

        if attempt_count >= self.MAX_ATTEMPTS_PER_CAUSE:
            return (
                False,
                f"Maximum repair attempts ({self.MAX_ATTEMPTS_PER_CAUSE}) reached for root cause: {cause.description}",
            )

        # Check consecutive attempts without measurable progress
        if len(history) >= self.MAX_CONSECUTIVE_NO_PROGRESS:
            recent = history[-self.MAX_CONSECUTIVE_NO_PROGRESS:]
            no_error_reduction = all(
                r.diagnostic_count_after >= r.diagnostic_count_before and r.result_status != "SUCCESS"
                for r in recent
            )
            repeated_diffs = len({r.diff_hash for r in recent}) == 1
            if no_error_reduction or repeated_diffs:
                return (
                    False,
                    f"Repair halted: {self.MAX_CONSECUTIVE_NO_PROGRESS} consecutive attempts without measurable progress.",
                )

        return True, "Proceed with repair attempt."

    def record_attempt(
        self,
        cause: RootCause,
        diff_text: str,
        modified_files: List[str],
        result_status: str,
        diag_count_before: int,
        diag_count_after: int,
    ) -> RepairAttempt:
        """Records a repair attempt and checks for cycles or repetition."""
        diff_h = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()[:16]
        norm_lines = [l.strip() for l in (diff_text or "").splitlines() if l.strip()]
        norm_h = hashlib.sha256("\n".join(norm_lines).encode("utf-8")).hexdigest()[:16]
        history = self._history_by_cause.setdefault(cause.signature, [])
        attempt_no = len(history) + 1

        seen_diffs = self._diff_hashes_by_cause.setdefault(cause.signature, set())
        seen_diffs.add(diff_h)
        seen_diffs.add(norm_h)

        attempt = RepairAttempt(
            attempt_number=attempt_no,
            cause_signature=cause.signature,
            proposed_diff=diff_text,
            diff_hash=diff_h,
            modified_files=modified_files,
            result_status=result_status,
            diagnostic_count_before=diag_count_before,
            diagnostic_count_after=diag_count_after,
            timestamp=time.time(),
        )
        history.append(attempt)
        return attempt

    def is_cyclic_diff(self, cause: RootCause, diff_text: str) -> bool:
        """Returns True if the proposed diff was already attempted for this root cause."""
        diff_h = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()[:16]
        norm_lines = [l.strip() for l in (diff_text or "").splitlines() if l.strip()]
        norm_h = hashlib.sha256("\n".join(norm_lines).encode("utf-8")).hexdigest()[:16]
        seen = self._diff_hashes_by_cause.get(cause.signature, set())
        return diff_h in seen or norm_h in seen

    STANDARD_FORGE_STAGES: List[str] = [
        "design",
        "scaffold",
        "build_editor",
        "content",
        "assemble_level_1",
        "scenario_gen",
        "automation",
        "package",
        "scenarios",
        "review",
        "report",
    ]

    STAGE_ALIASES: Dict[str, str] = {
        "spec": "design",
        "codegen": "build_editor",
        "sources": "build_editor",
        "build": "build_editor",
        "assemble": "assemble_level_1",
        "assemble_level": "assemble_level_1",
        "automation_tests": "automation",
        "scenario": "scenarios",
        "packaged_smoke": "scenarios",
    }

    def affected_downstream_stages(self, failed_stage_id: str) -> List[str]:
        """Calculates downstream stages in the canonical 11-stage pipeline."""
        canonical_id = self.STAGE_ALIASES.get(failed_stage_id, failed_stage_id)
        if canonical_id in self.STANDARD_FORGE_STAGES:
            idx = self.STANDARD_FORGE_STAGES.index(canonical_id)
            return self.STANDARD_FORGE_STAGES[idx:]
        return [failed_stage_id]

    def compute_invalidated_stages(
        self,
        failed_stage_id: str,
        all_stage_dependencies: Dict[str, List[str]],
    ) -> List[str]:
        """Calculates which downstream stages are invalidated and must be rerun."""
        invalidated: Set[str] = {failed_stage_id}
        changed = True
        while changed:
            changed = False
            for step_id, deps in all_stage_dependencies.items():
                if step_id not in invalidated and any(d in invalidated for d in deps):
                    invalidated.add(step_id)
                    changed = True

        return sorted(list(invalidated))


# Alias for callers expecting RepairSystem
RepairSystem = RepairEngine


def uuid_hex(val: str) -> str:
    return hashlib.sha256(val.encode()).hexdigest()[:12]
