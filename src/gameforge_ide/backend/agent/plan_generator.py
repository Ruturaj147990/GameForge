"""Natural-Language to Validated Dependency-Aware Plan Generator for GameForge IDE.

Converts complex natural-language requests into strictly validated directed acyclic graph (DAG) plans.
Rules:
- Maps tasks to actual supported operations and real tools in ToolGateway.
- Every task has machine-checkable acceptance criteria.
- Validates against circular dependencies, duplicate IDs, missing prerequisites.
- Supports deterministic archetypes and model-driven generation (using gameforge-qwen3.5-9b).
- Model cannot alter its own permissions or waive acceptance criteria.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..providers.router import ModelRouter
from ..tools.gateway import ToolGateway
from .task_plan import PlanValidationError, TaskNode, TaskPlan
from .task_state import TaskAcceptancePredicate

logger = logging.getLogger(__name__)


class PlanGenerator:
    """Generates validated TaskPlan DAGs from natural language or structured specifications."""

    def __init__(self, workspace_root: Path, tool_gateway: Optional[ToolGateway] = None, model_router: Optional[ModelRouter] = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.tool_gateway = tool_gateway or ToolGateway(self.workspace_root)
        self.model_router = model_router or ModelRouter()

    def generate_unreal_mutation_plan(
        self,
        goal: str,
        uproject_path: str,
        actor_label: str = "GF_PlanActor",
        actor_class: str = "StaticMeshActor",
        location: Optional[Dict[str, float]] = None,
        static_mesh: str = "/Engine/BasicShapes/Cube.Cube",
    ) -> TaskPlan:
        """Creates a verified 3-step DAG plan for real Unreal Editor inspection, mutation, and read-back."""
        loc = location or {"x": 150.0, "y": 0.0, "z": 50.0}
        plan = TaskPlan(
            goal=goal,
            metadata={"uproject": uproject_path, "archetype": "unreal_mutation"},
        )

        # Step 1: Read-only inspection of active level & editor
        task1 = TaskNode(
            task_id="step1_inspect",
            title=f"Inspect level actors and engine state in {Path(uproject_path).name}",
            objective=f"Query current level actors and engine identity for {uproject_path}",
            expected_result="Verified editor responsiveness and active level actor list",
            task_type="inspect",
            permitted_tools=["unreal_editor"],
            dependency_ids=[],
            reversibility="read-only",
            requires_approval=False,
            tool_call={
                "name": "unreal_editor",
                "arguments": {"uproject": uproject_path, "op": "actors_in_level", "args": {"limit": 100}},
            },
            acceptance=[
                TaskAcceptancePredicate(predicate_type="custom", target="editor_responsive"),
            ],
        )

        # Step 2: Serialized Unreal Editor mutation (requires approval)
        task2 = TaskNode(
            task_id="step2_mutate",
            title=f"Spawn actor '{actor_label}' in active level",
            objective=f"Spawn {actor_class} with label '{actor_label}' at location {loc} using mesh {static_mesh}",
            expected_result=f"Actor '{actor_label}' spawned in level",
            task_type="editor_op",
            permitted_tools=["unreal_editor"],
            dependency_ids=["step1_inspect"],
            reversibility="transactional",
            requires_approval=True,
            tool_call={
                "name": "unreal_editor",
                "arguments": {
                    "uproject": uproject_path,
                    "op": "spawn_actor",
                    "args": {
                        "actor_class": actor_class,
                        "label": actor_label,
                        "location": loc,
                        "static_mesh": static_mesh,
                    },
                },
            },
            acceptance=[
                TaskAcceptancePredicate(predicate_type="unreal_actor_exists", target=actor_label),
            ],
        )

        # Step 3: Read-back verification of level state
        task3 = TaskNode(
            task_id="step3_verify",
            title=f"Verify actor '{actor_label}' via editor read-back",
            objective=f"Confirm actor '{actor_label}' exists in active level with correct label and transform",
            expected_result=f"Actor '{actor_label}' read-back confirmed via actors_in_level",
            task_type="inspect",
            permitted_tools=["unreal_editor"],
            dependency_ids=["step2_mutate"],
            reversibility="read-only",
            requires_approval=False,
            tool_call={
                "name": "unreal_editor",
                "arguments": {"uproject": uproject_path, "op": "actors_in_level", "args": {"limit": 200}},
            },
            acceptance=[
                TaskAcceptancePredicate(predicate_type="unreal_actor_exists", target=actor_label),
            ],
        )

        plan.add_task(task1)
        plan.add_task(task2)
        plan.add_task(task3)
        plan.final_acceptance = [
            TaskAcceptancePredicate(predicate_type="unreal_actor_exists", target=actor_label)
        ]

        valid, errs = plan.validate()
        if not valid:
            raise PlanValidationError("; ".join(errs))

        return plan

    def generate_repo_task_plan(
        self,
        goal: str,
        target_file: str,
        target_snippet: str,
        replacement_snippet: str,
        test_command: str = "pytest tests/unit/test_task_plan.py -q",
    ) -> TaskPlan:
        """Creates a verified multi-step DAG plan for bounded code editing and test verification."""
        plan = TaskPlan(
            goal=goal,
            metadata={"target_file": target_file, "archetype": "repo_task"},
        )

        # Task 1: Inspect source file
        task1 = TaskNode(
            task_id="task1_inspect",
            title=f"Inspect target file {target_file}",
            objective=f"Verify target file {target_file} exists and contains target snippet",
            expected_result="File contents read and confirmed",
            task_type="inspect",
            permitted_tools=["read_file"],
            dependency_ids=[],
            reversibility="read-only",
            requires_approval=False,
            tool_call={"name": "read_file", "arguments": {"subpath": target_file}},
            acceptance=[
                TaskAcceptancePredicate(predicate_type="file_exists", target=target_file),
            ],
        )

        # Task 2: Propose and apply edit (requires approval)
        task2 = TaskNode(
            task_id="task2_edit",
            title=f"Apply modification to {target_file}",
            objective=f"Update {target_file} with replacement snippet",
            expected_result="File modified on disk with new content",
            task_type="mutate",
            permitted_tools=["propose_edit", "apply_edit"],
            dependency_ids=["task1_inspect"],
            reversibility="transactional",
            requires_approval=True,
            tool_call={
                "name": "propose_edit",
                "arguments": {
                    "subpath": target_file,
                    "target_content": target_snippet,
                    "replacement_content": replacement_snippet,
                },
            },
            acceptance=[
                TaskAcceptancePredicate(predicate_type="file_changed", target=target_file),
                TaskAcceptancePredicate(predicate_type="file_content_contains", target=target_file, expected=replacement_snippet.strip()[:30]),
            ],
        )

        # Task 3: Run real unit tests
        task3 = TaskNode(
            task_id="task3_test",
            title="Execute test suite to verify modification",
            objective=f"Run test command '{test_command}' to confirm zero regressions",
            expected_result="All targeted tests pass with exit code 0",
            task_type="test",
            permitted_tools=["run_command"],
            dependency_ids=["task2_edit"],
            reversibility="read-only",
            requires_approval=False,
            tool_call={"name": "run_command", "arguments": {"command": test_command}},
            acceptance=[
                TaskAcceptancePredicate(predicate_type="command_exit_code", target=test_command, expected=0),
            ],
        )

        plan.add_task(task1)
        plan.add_task(task2)
        plan.add_task(task3)
        plan.final_acceptance = [
            TaskAcceptancePredicate(predicate_type="file_changed", target=target_file),
            TaskAcceptancePredicate(predicate_type="command_exit_code", target=test_command, expected=0),
        ]

        valid, errs = plan.validate()
        if not valid:
            raise PlanValidationError("; ".join(errs))

        return plan

    def generate_plan_from_prompt(self, user_prompt: str, context: Optional[Dict[str, Any]] = None) -> TaskPlan:
        """Parses natural language prompt into an executable TaskPlan.

        Keyword-templated helper used by tests and demos only. The product creates plans through Forge (P2);
        do not call this from the IDE.
        """
        prompt_lower = user_prompt.lower()
        ctx = context or {}

        # 1. Check if Unreal Editor prompt
        uproject = ctx.get("uproject") or next(
            (p for p in self.workspace_root.glob("*.uproject")), None
        )

        if any(w in prompt_lower for w in ("unreal", "actor", "mesh", "level", "spawn", "ue5", "uproject")) and uproject:
            # Extract desired actor label if mentioned
            match = re.search(r"spawn\s+(?:actor\s+)?['\"]?(\w+)['\"]?", prompt_lower)
            label = match.group(1) if match else "GF_PlanActor"
            return self.generate_unreal_mutation_plan(
                goal=user_prompt,
                uproject_path=str(uproject),
                actor_label=label,
            )

        # 2. Check for code edit / repo task
        target_file_match = re.search(r"(?:in|file|edit)\s+([A-Za-z0-9_\-\./\\]+\.[a-zA-Z0-9]+)", user_prompt)
        if target_file_match:
            tfile = target_file_match.group(1).replace("\\", "/")
            return self.generate_repo_task_plan(
                goal=user_prompt,
                target_file=tfile,
                target_snippet="",
                replacement_snippet="",
            )

        # Default multi-step plan
        plan = TaskPlan(goal=user_prompt)
        task1 = TaskNode(
            task_id="step1_inspect",
            title="Inspect project workspace and context",
            objective="Discover files and configuration relevant to prompt",
            expected_result="Workspace state cataloged",
            task_type="inspect",
            permitted_tools=["list_dir", "read_file", "search_code"],
            tool_call={"name": "list_dir", "arguments": {"subpath": ".", "max_depth": 1}},
            dependency_ids=[],
            acceptance=[TaskAcceptancePredicate(predicate_type="custom", target="inspection_complete")],
        )
        plan.add_task(task1)
        return plan
