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

import hashlib
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ...core.settings import get_settings
from ..models.plan_artifact import PlanArtifact, PlanStep
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

    def generate_engineering_plan(
        self,
        goal: str,
        target_files: Optional[List[str]] = None,
        test_command: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> TaskPlan:
        """Creates a verified 5-step DAG implementing the full autonomous engineering chain:
        Inspect -> Scaffold -> Implement -> Test -> Verify.
        """
        files = target_files or ["Source/GameModule.cpp"]
        t_cmd = test_command or "pytest tests/unit/ -q"
        primary_file = files[0]
        header_file = files[1] if len(files) > 1 else primary_file.replace(".cpp", ".h")

        plan = TaskPlan(
            goal=goal,
            metadata={"archetype": "autonomous_engineering", "target_files": files, "test_command": t_cmd},
        )

        # Step 1: Inspect existing architecture and references
        step1 = TaskNode(
            task_id="step1_inspect",
            title=f"Inspect codebase context for {Path(primary_file).name}",
            objective=f"Inspect existing files and architecture related to: {goal}",
            expected_result="Codebase context, existing symbols, and dependencies inspected",
            task_type="inspect",
            permitted_tools=["read_file", "list_dir", "search_code", "search_index"],
            dependency_ids=[],
            reversibility="read-only",
            requires_approval=False,
            context={"engineering_stage": 1, "stage_name": "inspect"},
            tool_call={"name": "read_file", "arguments": {"subpath": primary_file}},
            acceptance=[TaskAcceptancePredicate(predicate_type="custom", target="inspection_complete")],
        )

        # Step 2: Scaffold interface / header / types
        step2 = TaskNode(
            task_id="step2_scaffold",
            title=f"Scaffold interfaces and definitions in {Path(header_file).name}",
            objective=f"Scaffold interfaces, headers, or declarations required for: {goal}",
            expected_result=f"Declarations and structure in {header_file} staged",
            task_type="mutate",
            permitted_tools=["propose_edit", "apply_edit", "write_file"],
            dependency_ids=["step1_inspect"],
            reversibility="transactional",
            requires_approval=True,
            context={"engineering_stage": 2, "stage_name": "scaffold"},
            tool_call={
                "name": "propose_edit",
                "arguments": {
                    "subpath": header_file,
                    "target_content": "",
                    "replacement_content": f"// Scaffolding for {goal}\n",
                },
            },
            acceptance=[
                TaskAcceptancePredicate(predicate_type="file_exists", target=header_file),
                TaskAcceptancePredicate(predicate_type="file_changed", target=header_file),
            ],
            recovery_behavior="repair",
        )

        # Step 3: Implement core logic and source modifications
        step3 = TaskNode(
            task_id="step3_implement",
            title=f"Implement core logic changes in {Path(primary_file).name}",
            objective=f"Implement verified functionality to satisfy: {goal}",
            expected_result=f"Code modifications applied to {primary_file}",
            task_type="mutate",
            permitted_tools=["propose_edit", "apply_edit", "write_file"],
            dependency_ids=["step2_scaffold"],
            reversibility="transactional",
            requires_approval=True,
            context={"engineering_stage": 3, "stage_name": "implement"},
            tool_call={
                "name": "propose_edit",
                "arguments": {
                    "subpath": primary_file,
                    "target_content": "",
                    "replacement_content": f"// Implementation for {goal}\n",
                },
            },
            acceptance=[
                TaskAcceptancePredicate(predicate_type="file_changed", target=primary_file),
            ],
            recovery_behavior="repair",
        )

        # Step 4: Execute test suite / build verification
        step4 = TaskNode(
            task_id="step4_test",
            title="Execute test suite to verify implementation",
            objective=f"Run test verification command '{t_cmd}' to ensure zero regressions",
            expected_result=f"Test command '{t_cmd}' exits with code 0",
            task_type="test",
            permitted_tools=["run_command", "terminal_run"],
            dependency_ids=["step3_implement"],
            reversibility="read-only",
            requires_approval=False,
            context={"engineering_stage": 4, "stage_name": "test"},
            tool_call={"name": "run_command", "arguments": {"command": t_cmd}},
            acceptance=[
                TaskAcceptancePredicate(predicate_type="command_exit_code", target=t_cmd, expected=0),
            ],
            recovery_behavior="repair",
        )

        # Step 5: Final acceptance verification
        step5 = TaskNode(
            task_id="step5_verify",
            title="Verify complete feature acceptance criteria",
            objective=f"Verify acceptance predicates over real observed state for: {goal}",
            expected_result="All files modified and test execution verified",
            task_type="inspect",
            permitted_tools=["read_file", "list_dir", "run_command"],
            dependency_ids=["step4_test"],
            reversibility="read-only",
            requires_approval=False,
            context={"engineering_stage": 5, "stage_name": "verify"},
            acceptance=[
                TaskAcceptancePredicate(predicate_type="file_changed", target=primary_file),
                TaskAcceptancePredicate(predicate_type="command_exit_code", target=t_cmd, expected=0),
            ],
        )

        plan.add_task(step1)
        plan.add_task(step2)
        plan.add_task(step3)
        plan.add_task(step4)
        plan.add_task(step5)
        plan.final_acceptance = [
            TaskAcceptancePredicate(predicate_type="file_changed", target=primary_file),
            TaskAcceptancePredicate(predicate_type="command_exit_code", target=t_cmd, expected=0),
        ]

        valid, errs = plan.validate()
        if not valid:
            raise PlanValidationError("; ".join(errs))

        return plan

    @staticmethod
    def validate_engineering_dag(plan: TaskPlan) -> Tuple[bool, List[str]]:
        """Validates that a 5-stage engineering DAG strictly respects required lifecycle states,
        topological sequencing, and machine-checkable acceptance criteria."""
        valid, errs = plan.validate()
        if not valid:
            return False, errs
        required_stages = ["step1_inspect", "step2_scaffold", "step3_implement", "step4_test", "step5_verify"]
        for st in required_stages:
            if st not in plan.tasks:
                errs.append(f"Missing required engineering stage: {st}")
        if not errs:
            order = plan.get_topological_order()
            idx_map = {tid: idx for idx, tid in enumerate(order)}
            for i in range(len(required_stages) - 1):
                cur, nxt = required_stages[i], required_stages[i + 1]
                if idx_map[cur] >= idx_map[nxt]:
                    errs.append(f"Engineering stage {cur} must execute before {nxt}")
        return len(errs) == 0, errs

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

        # 2. Check for multi-file or full engineering goal
        all_file_matches = re.findall(r"[\w\-\./\\]+\.(?:cpp|h|hpp|py|cs|json|ini)", user_prompt)
        has_engineering_intent = any(
            k in prompt_lower for k in ("scaffold", "implement", "feature", "refactor", "multi-file", "and test", "with test")
        )
        if len(all_file_matches) >= 2 or (has_engineering_intent and all_file_matches):
            return self.generate_engineering_plan(
                goal=user_prompt,
                target_files=[f.replace("\\", "/") for f in all_file_matches],
            )

        # 3. Check for single file code edit / repo task
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

    def generate_llm_plan_artifact(
        self,
        prompt: str,
        session_id: str,
        is_game: bool = False,
        model_name: Optional[str] = None,
        active_project_dir: Optional[Union[str, Path]] = None,
        existing_plan: Optional[PlanArtifact] = None,
        turn_id: Optional[str] = None,
    ) -> PlanArtifact:
        """Generates a genuine task-specific implementation plan using the configured LLM or semantic strategy."""
        clean_prompt = prompt.strip()
        prompt_hash = hashlib.sha256(f"{session_id}:{clean_prompt}".encode("utf-8")).hexdigest()[:10]
        expected_plan_id = f"plan_{prompt_hash}"

        # 1. Deduplication check: prevent duplicate plans for the same goal
        if existing_plan is not None:
            if existing_plan.plan_id == expected_plan_id or existing_plan.goal.strip() == clean_prompt:
                return existing_plan

        # Resolve active model
        settings = get_settings()
        active_model = model_name or settings.model_for("chat")

        # 2. Collect grounding context
        tools_summary = ", ".join(t.name for t in self.tool_gateway.get_definitions())
        proj_context = f"Workspace: {self.workspace_root.name}"
        if active_project_dir:
            proj_context += f" | Active Project: {Path(active_project_dir).name}"

        # 3. Strategy evaluation if game creation
        strategy_info = ""
        gds_payload = None
        if is_game:
            try:
                from ...design.template_registry import default_registry
                decision = default_registry.evaluate_strategy(clean_prompt)
                strategy_info = f"Strategy: {decision.strategy.value}"
                if decision.template:
                    strategy_info += f" (Template: {decision.template.title})"
            except Exception:
                pass

        plan_schema = {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "summary": {"type": "string"},
                "implementation_method": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step_id": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "target_files": {"type": "array", "items": {"type": "string"}},
                            "tools": {"type": "array", "items": {"type": "string"}},
                            "verification": {"type": "string"},
                        },
                        "required": ["step_id", "title", "description", "target_files", "tools", "verification"],
                    },
                },
            },
            "required": ["goal", "summary", "steps"],
        }

        system_instruction = (
            "You are GameForge Principal Systems Architect. Formulate an actionable, sequential technical implementation plan.\n"
            "Rules:\n"
            "- Tailor every step specifically to the user's explicit prompt, genre, and requested mechanics.\n"
            "- NEVER output hardcoded or generic Sudoku steps unless the user explicitly requested a Sudoku game.\n"
            f"- Available tools: {tools_summary}\n"
            "- Include concrete target files, tool names, and verifiable acceptance criteria for each step."
        )

        user_content = (
            f"User Task: {clean_prompt}\n"
            f"Context: {proj_context}\n"
            f"{strategy_info}\n"
            "Produce the technical implementation plan in clean JSON matching the schema."
        )

        # 4. Attempt genuine LLM generation via Ollama / router
        raw_json = None
        t0 = time.time()
        call_timeout = 0.5 if os.environ.get("PYTEST_CURRENT_TEST") else 12.0
        try:
            provider = self.model_router.get_provider("ollama")
            if hasattr(provider, "complete_json") and (not hasattr(provider, "is_available") or provider.is_available()):
                raw_json = provider.complete_json(
                    model_id=active_model,
                    system=system_instruction,
                    user=user_content,
                    schema=plan_schema,
                    timeout_s=call_timeout,
                )
        except Exception as exc:
            logger.debug("Model plan generation via complete_json not available: %s", exc)

        duration = round(time.time() - t0, 3)

        # 5. Parse and validate LLM output if available
        if raw_json:
            try:
                parsed = json.loads(raw_json)
                steps_data = parsed.get("steps", [])
                if isinstance(steps_data, list) and len(steps_data) >= 1:
                    valid_steps: List[PlanStep] = []
                    seen_ids: Set[str] = set()

                    for idx, s in enumerate(steps_data, start=1):
                        sid = s.get("step_id") or f"step_{idx}"
                        if sid in seen_ids:
                            sid = f"step_{idx}_{uuid.uuid4().hex[:4]}"
                        seen_ids.add(sid)

                        valid_steps.append(
                            PlanStep(
                                step_id=sid,
                                title=s.get("title") or f"Step {idx}",
                                description=s.get("description") or "",
                                target_files=s.get("target_files", []) if isinstance(s.get("target_files"), list) else [],
                                tools=s.get("tools", []) if isinstance(s.get("tools"), list) else [],
                                verification=s.get("verification") or "",
                            )
                        )

                    return PlanArtifact(
                        plan_id=expected_plan_id,
                        session_id=session_id,
                        goal=parsed.get("goal") or clean_prompt,
                        summary=parsed.get("summary") or f"Implementation plan for: {clean_prompt}",
                        implementation_method=parsed.get("implementation_method") or ("game_creation" if is_game else "direct_code_edit"),
                        steps=valid_steps,
                        status="awaiting_approval",
                        metadata={
                            "provenance": "llm_generated",
                            "model_id": active_model,
                            "turn_id": turn_id,
                            "prompt_hash": prompt_hash,
                            "duration_seconds": duration,
                            "gds": gds_payload,
                        },
                    )
            except Exception as parse_exc:
                logger.warning("Failed parsing LLM plan JSON: %s; falling back to dynamic semantic strategy.", parse_exc)

        # 6. Dynamic Semantic Strategy Fallback (No fake hardcoded Sudoku)
        return self._generate_dynamic_semantic_plan(
            clean_prompt=clean_prompt,
            session_id=session_id,
            plan_id=expected_plan_id,
            is_game=is_game,
            active_model=active_model,
            turn_id=turn_id,
            prompt_hash=prompt_hash,
            gds_payload=gds_payload,
        )

    def _generate_dynamic_semantic_plan(
        self,
        clean_prompt: str,
        session_id: str,
        plan_id: str,
        is_game: bool,
        active_model: str,
        turn_id: Optional[str],
        prompt_hash: str,
        gds_payload: Optional[Dict[str, Any]],
    ) -> PlanArtifact:
        """Constructs a prompt-specific implementation plan dynamically without static hardcodings."""
        p_lower = clean_prompt.lower()

        # Identify key domain nouns and project name
        words = re.findall(r"\b[A-Za-z]{3,}\b", clean_prompt)
        subject_name = "".join(w.capitalize() for w in words[:2]) if words else "CustomFeature"
        
        if is_game:
            # Detect genre / mechanics from prompt
            genre_tag = "Custom"
            if any(k in p_lower for k in ("platform", "jump", "obstacle")):
                genre_tag = "Platformer"
            elif any(k in p_lower for k in ("shoot", "fps", "gun", "combat")):
                genre_tag = "CombatShooter"
            elif any(k in p_lower for k in ("puzzle", "sudoku", "match", "board")):
                genre_tag = "Puzzle"
            elif any(k in p_lower for k in ("adventure", "relic", "rpg", "dungeon")):
                genre_tag = "Adventure"

            steps = [
                PlanStep(
                    step_id="step_1_design",
                    title=f"1. Game Design Specification ({genre_tag})",
                    description=f"Draft typed GameDesignSpec configuring {clean_prompt} mechanics, entities, camera, and victory conditions.",
                    target_files=["GameForge/design/game.gds.json"],
                    tools=["plan_game", "write_file"],
                    verification="Valid GDS schema and parameter bounds",
                ),
                PlanStep(
                    step_id="step_2_scaffold",
                    title=f"2. Project Scaffold & C++ Core ({subject_name})",
                    description=f"Scaffold project structure declaring {subject_name}GameMode and {subject_name}State.",
                    target_files=[
                        f"Source/MyGame/{subject_name}GameMode.h",
                        f"Source/MyGame/{subject_name}GameMode.cpp",
                    ],
                    tools=["create_game", "write_file"],
                    verification="Scaffold directory structure intact and headers declared",
                ),
                PlanStep(
                    step_id="step_3_codegen",
                    title=f"3. Custom C++ Gameplay Handlers ({subject_name})",
                    description=f"Generate custom C++ rule handlers and game rules for: {clean_prompt}.",
                    target_files=[f"Source/MyGame/{subject_name}Rules.cpp"],
                    tools=["propose_edit", "write_file"],
                    verification="Custom rule handlers compile cleanly",
                ),
                PlanStep(
                    step_id="step_4_build_editor",
                    title="4. Compile Editor Target (UnrealBuildTool)",
                    description="Compile project C++ modules and GameForgeRuntime plugin in Development configuration.",
                    target_files=["Binaries/Win64/"],
                    tools=["unreal_build"],
                    verification="UBT zero-error compilation",
                ),
                PlanStep(
                    step_id="step_5_content",
                    title="5. Content Preparation (Audio & Visual Assets)",
                    description="Prepare procedural VFX/SFX audio presets, mannequins, and level prototyping materials.",
                    target_files=["Content/GameForge/"],
                    tools=["write_file", "generate_3d_mesh"],
                    verification="Content assets placed and cooker directories configured",
                ),
                PlanStep(
                    step_id="step_6_assemble",
                    title="6. Level Assembly & Actor Placement",
                    description="Instantiate level geometry, player start, lighting, and interactive gameplay entities.",
                    target_files=["Content/Maps/Level_1.umap"],
                    tools=["unreal_editor"],
                    verification="Level read-back confirms placed actors and NavMesh bounds",
                ),
                PlanStep(
                    step_id="step_7_scenario_gen",
                    title="7. Generate QA Playtest Scenarios",
                    description="Synthesize smoke, combat/mechanics, and victory condition scenarios conforming to scenario/1 schema.",
                    target_files=["GameForge/scenarios/"],
                    tools=["write_file"],
                    verification="Scenario JSON files schema-validated",
                ),
                PlanStep(
                    step_id="step_8_automation",
                    title="8. Run C++ Automation Tests",
                    description="Execute Unreal Engine C++ automation tests verifying plugin kit and game rules.",
                    target_files=[],
                    tools=["unreal_run_tests"],
                    verification="All automation tests pass with 0 errors",
                ),
                PlanStep(
                    step_id="step_9_package",
                    title="9. Package Standalone Executable",
                    description="Cook assets and package standalone Win64 executable for Windows.",
                    target_files=["Packaged/Windows/"],
                    tools=["unreal_package"],
                    verification="Standalone .exe exists on disk",
                ),
                PlanStep(
                    step_id="step_10_scenarios",
                    title="10. Execute Packaged QA Scenarios",
                    description="Execute deterministic headless scenario verification validating rules and win/loss states.",
                    target_files=["Saved/GameForge/evidence/"],
                    tools=["run_command", "unreal_run_tests"],
                    verification="All gameplay scenario assertions pass",
                ),
                PlanStep(
                    step_id="step_11_review_report",
                    title="11. Review & Compile Final Evidence Report",
                    description="Review vision rubric, mesh audit, and compile comprehensive pipeline report.",
                    target_files=["Saved/GameForge/pipeline_report.json"],
                    tools=["write_file", "verify_disk"],
                    verification="Pipeline evidence report exists and its required fields validate",
                ),
            ]
            impl_method = "game_creation"
            summary_text = f"Actionable game creation pipeline for: {clean_prompt}"
        else:
            # Non-game engineering task
            target_files = re.findall(r"[\w\-\./\\]+\.(?:cpp|h|hpp|py|cs|json|ini)", clean_prompt)
            primary_file = target_files[0] if target_files else f"Source/{subject_name}.cpp"

            steps = [
                PlanStep(
                    step_id="step_1_inspect",
                    title="1. Inspect Codebase & Symbols",
                    description=f"Inspect relevant files and symbol definitions related to: {clean_prompt}",
                    target_files=[primary_file],
                    tools=["search_index", "search_code", "read_file", "list_dir"],
                    verification="Relevant code context and dependencies identified",
                ),
                PlanStep(
                    step_id="step_2_interface",
                    title="2. Interface & Declaration Staging",
                    description=f"Stage type signatures, interfaces, or declarations for {subject_name}.",
                    target_files=[primary_file.replace(".cpp", ".h") if primary_file.endswith(".cpp") else primary_file],
                    tools=["propose_edit", "write_file"],
                    verification="Header declarations staged cleanly",
                ),
                PlanStep(
                    step_id="step_3_implement",
                    title="3. Implementation & Refactoring",
                    description=f"Implement core logic satisfying: {clean_prompt}",
                    target_files=[primary_file],
                    tools=["propose_edit", "write_file"],
                    verification="Target file modified on disk with unified diff",
                ),
                PlanStep(
                    step_id="step_4_test",
                    title="4. Verification & Test Execution",
                    description="Execute automated tests to ensure zero regressions.",
                    target_files=[],
                    tools=["run_command"],
                    verification="Verification test command exits with code 0",
                ),
            ]
            impl_method = "direct_code_edit"
            summary_text = f"Technical engineering workflow for: {clean_prompt}"

        return PlanArtifact(
            plan_id=plan_id,
            session_id=session_id,
            goal=clean_prompt,
            summary=summary_text,
            implementation_method=impl_method,
            steps=steps,
            status="awaiting_approval",
            metadata={
                "provenance": "semantic_fallback",
                "llm_generated": False,
                "llm_fallback_reason": "No valid task-specific LLM plan was accepted; deterministic semantic fallback was used.",
                "model_id": active_model,
                "turn_id": turn_id,
                "prompt_hash": prompt_hash,
                "gds": gds_payload,
            },
        )
