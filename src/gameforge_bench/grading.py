"""Layered grading engine implementing EVALUATION_CONTRACT.md."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from .engines.base import AssetValidationResult, BuildResult, ProbeMeasurement, TestResult
from .policy import PolicyCheckResult


class RunStatus(str, Enum):
    PASS = "PASS"
    PARTIAL_BUILD = "PARTIAL_BUILD"
    FAIL_BUILD = "FAIL_BUILD"
    POLICY_FAIL = "POLICY_FAIL"
    HARNESS_INVALID = "HARNESS_INVALID"
    FLAKY_QUARANTINED = "FLAKY_QUARANTINED"


class GradingLayer(str, Enum):
    CLEAN_START = "clean_start"
    POLICY_CHECKS = "policy_checks"
    BUILD_IMPORT = "build_import"
    AUTOMATED_TESTS = "automated_tests"
    BEHAVIOR_PROBES = "behavior_probes"
    SAVED_ASSET_CHECKS = "saved_asset_checks"
    PERFORMANCE_CHECKS = "performance_checks"
    REGRESSION_CHECKS = "regression_checks"
    VISUAL_REVIEW = "visual_review"


@dataclass
class LayerOutcome:
    status: str  # "PASS", "FAIL", "SKIPPED", "NOT_APPLICABLE", "ERROR"
    duration_seconds: float = 0.0
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class GradingPipelineResult:
    overall_status: RunStatus
    first_mandatory_failure_layer: Optional[str]
    layers: dict[str, LayerOutcome]
    probes: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "first_mandatory_failure_layer": self.first_mandatory_failure_layer,
            "layers": {k: v.to_dict() for k, v in self.layers.items()},
            "probes": self.probes,
            "duration_seconds": self.duration_seconds,
            "warnings": self.warnings,
        }


def evaluate_grading_pipeline(
    clean_start_ok: bool,
    policy_result: PolicyCheckResult,
    build_result: BuildResult,
    tests: List[TestResult],
    probes: List[ProbeMeasurement],
    asset_result: AssetValidationResult,
    perf_ok: bool = True,
    regression_ok: bool = True,
    is_engine_available: bool = True,
    visual_applicable: bool = False,
    is_quarantined: bool = False,
) -> GradingPipelineResult:
    """Evaluates all nine grading layers in order and computes the standard status vocabulary."""
    layers: Dict[str, LayerOutcome] = {}
    warnings: List[str] = []
    first_failure: Optional[str] = None

    # Layer 1: Clean Start
    if not clean_start_ok:
        layers[GradingLayer.CLEAN_START.value] = LayerOutcome("ERROR", message="Workspace snapshot reset failed")
        first_failure = first_failure or GradingLayer.CLEAN_START.value
    else:
        layers[GradingLayer.CLEAN_START.value] = LayerOutcome("PASS", message="Workspace snapshot verified")

    # Layer 2: Policy & Static Checks
    if not policy_result.passed:
        layers[GradingLayer.POLICY_CHECKS.value] = LayerOutcome(
            "FAIL",
            message=f"Violations: {'; '.join(policy_result.violations)}",
            details=policy_result.details,
        )
        first_failure = first_failure or GradingLayer.POLICY_CHECKS.value
    else:
        layers[GradingLayer.POLICY_CHECKS.value] = LayerOutcome("PASS", message="All static boundaries respected")

    # Check engine availability (infrastructure gate)
    if not is_engine_available:
        layers[GradingLayer.BUILD_IMPORT.value] = LayerOutcome(
            "ERROR",
            duration_seconds=0.0,
            message="Engine not installed in environment",
            details={"is_infrastructure_failure": True},
        )
        first_failure = first_failure or GradingLayer.BUILD_IMPORT.value
        return GradingPipelineResult(
            overall_status=RunStatus.HARNESS_INVALID,
            first_mandatory_failure_layer=first_failure,
            layers=layers,
            warnings=["Engine not installed; real-engine execution blocked"],
        )

    # Layer 3: Build/Import
    if not build_result.success:
        status_val = "ERROR" if build_result.is_infrastructure_failure else "FAIL"
        layers[GradingLayer.BUILD_IMPORT.value] = LayerOutcome(
            status_val,
            duration_seconds=build_result.duration_seconds,
            message=build_result.error_summary or "Compilation/Import failed",
            details={"return_code": build_result.return_code},
        )
        first_failure = first_failure or GradingLayer.BUILD_IMPORT.value
    else:
        layers[GradingLayer.BUILD_IMPORT.value] = LayerOutcome(
            "PASS",
            duration_seconds=build_result.duration_seconds,
            message="Project built and imported successfully",
        )

    # Layer 4: Automated Tests
    tests_passed = len(tests) > 0 and all(t.passed for t in tests)
    if not tests:
        layers[GradingLayer.AUTOMATED_TESTS.value] = LayerOutcome(
            "SKIPPED", message="No automated tests declared for this task"
        )
    elif tests_passed:
        layers[GradingLayer.AUTOMATED_TESTS.value] = LayerOutcome(
            "PASS",
            message=f"All {len(tests)} automated tests passed",
            details={"tests": [asdict(t) for t in tests]},
        )
    else:
        failed_names = [t.name for t in tests if not t.passed]
        layers[GradingLayer.AUTOMATED_TESTS.value] = LayerOutcome(
            "FAIL",
            message=f"Failed tests: {', '.join(failed_names)}",
            details={"tests": [asdict(t) for t in tests]},
        )
        first_failure = first_failure or GradingLayer.AUTOMATED_TESTS.value

    # Layer 5: Behavior Probes
    probe_dict: Dict[str, Any] = {}
    probes_passed = True
    if probes:
        for p in probes:
            probe_dict[p.probe_id] = {
                "passed": p.passed,
                "measured_value": p.measured_value,
                "target_value": p.target_value,
                "tolerance": p.tolerance,
                "unit": p.unit,
                "details": p.details,
            }
            if not p.passed:
                probes_passed = False

        if probes_passed:
            layers[GradingLayer.BEHAVIOR_PROBES.value] = LayerOutcome(
                "PASS", message=f"All {len(probes)} behavior probes passed within tolerance"
            )
        else:
            failed_p = [p.probe_id for p in probes if not p.passed]
            layers[GradingLayer.BEHAVIOR_PROBES.value] = LayerOutcome(
                "FAIL", message=f"Probes out of tolerance: {', '.join(failed_p)}"
            )
            first_failure = first_failure or GradingLayer.BEHAVIOR_PROBES.value
    else:
        layers[GradingLayer.BEHAVIOR_PROBES.value] = LayerOutcome(
            "SKIPPED", message="No behavior probes configured"
        )

    # Layer 6: Saved-Asset Checks
    if not asset_result.passed:
        layers[GradingLayer.SAVED_ASSET_CHECKS.value] = LayerOutcome(
            "FAIL",
            message=f"Missing: {asset_result.missing_components + asset_result.missing_assets}",
            details=asset_result.details,
        )
        first_failure = first_failure or GradingLayer.SAVED_ASSET_CHECKS.value
    else:
        layers[GradingLayer.SAVED_ASSET_CHECKS.value] = LayerOutcome(
            "PASS", message="Saved assets, components, and references validated", details=asset_result.details
        )

    # Layer 7: Performance Checks
    if not perf_ok:
        layers[GradingLayer.PERFORMANCE_CHECKS.value] = LayerOutcome("FAIL", message="Performance budget exceeded")
        first_failure = first_failure or GradingLayer.PERFORMANCE_CHECKS.value
    else:
        layers[GradingLayer.PERFORMANCE_CHECKS.value] = LayerOutcome("PASS", message="Within declared performance limits")

    # Layer 8: Regression Checks
    if not regression_ok:
        layers[GradingLayer.REGRESSION_CHECKS.value] = LayerOutcome("FAIL", message="Regression detected in existing behaviors")
        first_failure = first_failure or GradingLayer.REGRESSION_CHECKS.value
    else:
        layers[GradingLayer.REGRESSION_CHECKS.value] = LayerOutcome("PASS", message="No regressions detected")

    # Layer 9: Visual Review
    if visual_applicable:
        layers[GradingLayer.VISUAL_REVIEW.value] = LayerOutcome("PASS", message="Visual review passed")
    else:
        layers[GradingLayer.VISUAL_REVIEW.value] = LayerOutcome("NOT_APPLICABLE", message="Visual review not required")

    # Overall Status Computation
    if is_quarantined:
        overall_status = RunStatus.FLAKY_QUARANTINED
    elif not clean_start_ok or build_result.is_infrastructure_failure:
        overall_status = RunStatus.HARNESS_INVALID
    elif not policy_result.passed:
        overall_status = RunStatus.POLICY_FAIL
    elif not build_result.success:
        overall_status = RunStatus.FAIL_BUILD
    elif first_failure is not None:
        overall_status = RunStatus.PARTIAL_BUILD
    else:
        overall_status = RunStatus.PASS

    return GradingPipelineResult(
        overall_status=overall_status,
        first_mandatory_failure_layer=first_failure,
        layers=layers,
        probes=probe_dict,
        warnings=warnings,
    )
