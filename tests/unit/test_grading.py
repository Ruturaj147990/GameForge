"""Unit tests for the 9-layer grading pipeline and status vocabulary."""

from gameforge_bench.engines.base import (
    AssetValidationResult,
    BuildResult,
    ProbeMeasurement,
    TestResult,
)
from gameforge_bench.grading import GradingLayer, RunStatus, evaluate_grading_pipeline
from gameforge_bench.policy import PolicyCheckResult


def test_grading_pipeline_all_pass():
    policy = PolicyCheckResult(passed=True)
    build = BuildResult(success=True, duration_seconds=1.2, return_code=0, log_output="ok")
    tests = [TestResult(name="t1", passed=True, duration_seconds=0.1)]
    probes = [
        ProbeMeasurement(
            probe_id="speed",
            target_value=6.0,
            measured_value=6.0,
            tolerance=0.3,
            passed=True,
            unit="m/s",
        )
    ]
    assets = AssetValidationResult(passed=True)

    res = evaluate_grading_pipeline(
        clean_start_ok=True,
        policy_result=policy,
        build_result=build,
        tests=tests,
        probes=probes,
        asset_result=assets,
    )

    assert res.overall_status == RunStatus.PASS
    assert res.first_mandatory_failure_layer is None
    assert res.layers[GradingLayer.CLEAN_START.value].status == "PASS"
    assert res.layers[GradingLayer.BUILD_IMPORT.value].status == "PASS"
    assert res.layers[GradingLayer.AUTOMATED_TESTS.value].status == "PASS"
    assert res.layers[GradingLayer.BEHAVIOR_PROBES.value].status == "PASS"


def test_grading_pipeline_partial_build_when_probe_fails():
    policy = PolicyCheckResult(passed=True)
    build = BuildResult(success=True, duration_seconds=1.2, return_code=0, log_output="ok")
    tests = [TestResult(name="t1", passed=True, duration_seconds=0.1)]
    # Probe out of tolerance
    probes = [
        ProbeMeasurement(
            probe_id="speed",
            target_value=6.0,
            measured_value=2.5,
            tolerance=0.3,
            passed=False,
            unit="m/s",
        )
    ]
    assets = AssetValidationResult(passed=True)

    res = evaluate_grading_pipeline(
        clean_start_ok=True,
        policy_result=policy,
        build_result=build,
        tests=tests,
        probes=probes,
        asset_result=assets,
    )

    # Behavior matters more than compilation: partial build, not pass
    assert res.overall_status == RunStatus.PARTIAL_BUILD
    assert res.first_mandatory_failure_layer == GradingLayer.BEHAVIOR_PROBES.value
    assert res.layers[GradingLayer.BUILD_IMPORT.value].status == "PASS"
    assert res.layers[GradingLayer.BEHAVIOR_PROBES.value].status == "FAIL"


def test_grading_pipeline_fail_build():
    policy = PolicyCheckResult(passed=True)
    build = BuildResult(
        success=False,
        duration_seconds=1.0,
        return_code=1,
        log_output="syntax error",
        error_summary="syntax error",
    )

    res = evaluate_grading_pipeline(
        clean_start_ok=True,
        policy_result=policy,
        build_result=build,
        tests=[],
        probes=[],
        asset_result=AssetValidationResult(passed=True),
    )

    assert res.overall_status == RunStatus.FAIL_BUILD
    assert res.first_mandatory_failure_layer == GradingLayer.BUILD_IMPORT.value


def test_grading_pipeline_policy_fail():
    policy = PolicyCheckResult(passed=False, violations=["Tampering with grader detected"])
    build = BuildResult(success=True, duration_seconds=1.0, return_code=0, log_output="ok")

    res = evaluate_grading_pipeline(
        clean_start_ok=True,
        policy_result=policy,
        build_result=build,
        tests=[],
        probes=[],
        asset_result=AssetValidationResult(passed=True),
    )

    assert res.overall_status == RunStatus.POLICY_FAIL
    assert res.first_mandatory_failure_layer == GradingLayer.POLICY_CHECKS.value


def test_grading_pipeline_harness_invalid():
    # If clean start fails or engine not available
    policy = PolicyCheckResult(passed=True)
    build = BuildResult(success=False, duration_seconds=0.0, return_code=-1, log_output="failed", is_infrastructure_failure=True)

    res = evaluate_grading_pipeline(
        clean_start_ok=False,
        policy_result=policy,
        build_result=build,
        tests=[],
        probes=[],
        asset_result=AssetValidationResult(passed=True),
    )

    assert res.overall_status == RunStatus.HARNESS_INVALID
