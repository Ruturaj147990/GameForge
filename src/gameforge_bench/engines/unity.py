"""Unity Engine Adapter implementation for GameForge Benchmark."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from .discovery import discover_unity_engine


class UnityEngineAdapter(EngineAdapter):
    """Adapter for Unity projects and batchmode automated grading."""

    def __init__(self, engine_discovery: Optional[EngineDiscoveryResult] = None):
        self._discovery = engine_discovery or discover_unity_engine()

    @property
    def engine_name(self) -> str:
        return "unity"

    def discover(self) -> EngineDiscoveryResult:
        if not self._discovery or not self._discovery.is_installed:
            self._discovery = discover_unity_engine()
        return self._discovery

    def validate_project_structure(self, project_path: Path) -> Tuple[bool, str]:
        if not project_path.is_dir():
            return False, f"Project directory does not exist: {project_path}"

        assets_dir = project_path / "Assets"
        proj_settings = project_path / "ProjectSettings"

        if not assets_dir.is_dir():
            return False, f"Missing 'Assets' directory in Unity project: {project_path}"

        if not proj_settings.is_dir():
            return False, f"Missing 'ProjectSettings' directory in Unity project: {project_path}"

        version_file = proj_settings / "ProjectVersion.txt"
        if not version_file.is_file():
            return False, f"Missing 'ProjectSettings/ProjectVersion.txt' in Unity project: {project_path}"

        return True, "Valid Unity project structure"

    def prepare_clean_workspace(self, fixture_path: Path, target_path: Path) -> None:
        """Copies fixture project to target path, removing volatile Library/Temp folders."""
        if target_path.exists():
            shutil.rmtree(target_path, ignore_errors=True)

        shutil.copytree(fixture_path, target_path)

        for folder_name in ("Library", "Temp", "Obj", "Build", "Builds", "Logs", "MemoryCaptures"):
            volatile_dir = target_path / folder_name
            if volatile_dir.exists():
                shutil.rmtree(volatile_dir, ignore_errors=True)

    def build_batchmode_args(
        self,
        project_path: Path,
        log_file: Path,
        execute_method: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ) -> List[str]:
        """Constructs safe array arguments for Unity Editor batchmode execution."""
        exe = self._discovery.executable_path or "Unity.exe"
        cmd = [
            exe,
            "-batchmode",
            "-nographics",
            "-quit",
            "-projectPath",
            str(project_path),
            "-logFile",
            str(log_file),
        ]
        if execute_method:
            cmd.extend(["-executeMethod", execute_method])
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    def build_project(self, project_path: Path, log_dir: Path) -> BuildResult:
        """Executes Unity batchmode compilation and asset import."""
        if not self._discovery.is_installed or not self._discovery.executable_path:
            return BuildResult(
                success=False,
                duration_seconds=0.0,
                return_code=-1,
                log_output="Unity Editor is not installed in the local environment. Real-engine Unity execution is UNVERIFIED.",
                error_summary="Unity Editor unavailable",
                is_infrastructure_failure=True,
            )

        log_file = log_dir / "unity_build.log"
        cmd = self.build_batchmode_args(project_path, log_file)

        res = safe_subprocess_run(cmd, cwd=project_path, timeout_seconds=300, log_dir=log_dir, log_prefix="unity_build")

        log_content = res.stdout + "\n" + res.stderr
        if log_file.is_file():
            try:
                log_content += "\n" + log_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

        success = (res.return_code == 0) and ("Scripts have compiler errors" not in log_content)
        return BuildResult(
            success=success,
            duration_seconds=res.duration_seconds,
            return_code=res.return_code,
            log_output=log_content,
            error_summary=None if success else "Unity batchmode build failed",
            is_infrastructure_failure=False,
        )

    def execute_automated_tests(self, project_path: Path, log_dir: Path) -> List[TestResult]:
        """Runs Unity Test Framework (UTF) in batchmode."""
        if not self._discovery.is_installed or not self._discovery.executable_path:
            return [
                TestResult(
                    name="unity_test_framework",
                    passed=False,
                    duration_seconds=0.0,
                    message="Unity Editor is not installed. Test execution unverified.",
                )
            ]

        results_xml = log_dir / "unity_test_results.xml"
        log_file = log_dir / "unity_tests.log"
        extra = [
            "-runTests",
            "-testPlatform",
            "EditMode",
            "-testResults",
            str(results_xml),
        ]
        cmd = self.build_batchmode_args(project_path, log_file, extra_args=extra)
        res = safe_subprocess_run(cmd, cwd=project_path, timeout_seconds=300, log_dir=log_dir, log_prefix="unity_tests")

        return [
            TestResult(
                name="unity_editmode_tests",
                passed=(res.return_code == 0),
                duration_seconds=res.duration_seconds,
                message="Tests executed" if res.return_code == 0 else f"Failed with exit code {res.return_code}",
            )
        ]

    def execute_behavior_probes(
        self, project_path: Path, log_dir: Path, acceptance_config: Dict[str, Any]
    ) -> List[ProbeMeasurement]:
        """Executes runtime gameplay behavior probes for Unity."""
        if not self._discovery.is_installed:
            return [
                ProbeMeasurement(
                    probe_id="unity_runtime_probes",
                    target_value="executable",
                    measured_value="unverified",
                    tolerance=None,
                    passed=False,
                    details="Unity Editor is not installed locally. Behavior probes cannot execute on real engine.",
                )
            ]

        return [
            ProbeMeasurement(
                probe_id="unity_movement_speed",
                target_value=acceptance_config.get("kinematics", {}).get("max_run_speed_mps", {}).get("target", 6.0),
                measured_value="not_measured",
                tolerance=acceptance_config.get("kinematics", {}).get("max_run_speed_mps", {}).get("tolerance", 0.3),
                passed=False,
                details="Unity runner placeholder; real editor unverified.",
            )
        ]

    def inspect_saved_assets(
        self, project_path: Path, acceptance_config: Dict[str, Any]
    ) -> AssetValidationResult:
        """Inspects Unity assets, scenes, meta files, and component scripts."""
        is_valid, reason = self.validate_project_structure(project_path)
        if not is_valid:
            return AssetValidationResult(
                passed=False,
                missing_assets=[reason],
                details={"error": reason},
            )

        missing_components: List[str] = []
        missing_assets: List[str] = []
        unresolved_refs: List[str] = []

        # Check required scripts / components in Assets/
        assets_dir = project_path / "Assets"
        csharp_scripts = list(assets_dir.glob("**/*.cs"))
        script_contents = ""
        for cs in csharp_scripts:
            try:
                script_contents += cs.read_text(encoding="utf-8", errors="replace") + "\n"
            except Exception:
                pass

        req_components = acceptance_config.get("required_components", [])
        for comp in req_components:
            # Map Unreal component names to Unity equivalents if needed
            unity_equiv = comp
            if comp == "CharacterMovementComponent":
                unity_equiv = "CharacterController"
            elif comp == "SpringArmComponent":
                unity_equiv = "Camera"

            if unity_equiv not in script_contents and not any(unity_equiv.lower() in p.name.lower() for p in csharp_scripts):
                missing_components.append(f"Unity:{unity_equiv}")

        passed = (len(missing_components) == 0) and (len(missing_assets) == 0)
        return AssetValidationResult(
            passed=passed,
            missing_components=missing_components,
            missing_assets=missing_assets,
            unresolved_references=unresolved_refs,
            details={
                "csharp_script_count": len(csharp_scripts),
                "unity_version": (project_path / "ProjectSettings" / "ProjectVersion.txt").read_text(encoding="utf-8").strip(),
            },
        )
