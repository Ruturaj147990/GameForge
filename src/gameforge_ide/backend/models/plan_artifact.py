"""Structured, Actionable Plan Artifact and Multi-Turn Revision Model for GameForge 1.0.

Conforms to GameForge 1.0 Master Transformation Directive:
- Section 2.5: Planning mode for substantial tasks (new game creation, complex modifications,
  major features, multi-file refactoring, complex debugging, architecture work).
- Assistant generates a technical, actionable plan rendered as an artifact in chat.
- User can send additional prompts to revise the same plan without creating an unrelated new task.
- Preserves agreed requirements, reconciles changes, and updates the plan.
- Single Proceed/Execute confirmation starts implementation.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


PlanStepStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
PlanArtifactStatus = Literal["draft", "awaiting_approval", "approved", "executing", "completed", "failed", "rejected"]


class PlanStep(BaseModel):
    """An individual actionable step in an engineering or game-development plan."""
    step_id: str = Field(default_factory=lambda: f"step_{uuid.uuid4().hex[:6]}")
    title: str
    description: str
    target_files: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    verification: str = ""
    status: PlanStepStatus = "pending"
    error: Optional[str] = None
    output_summary: Optional[str] = None


class PlanRevision(BaseModel):
    """Records one turn of user revision to the plan."""
    version: int
    user_prompt: str
    summary_of_changes: str
    timestamp: float = Field(default_factory=time.time)


class PlanArtifact(BaseModel):
    """Authoritative technical plan artifact rendered and iteratively revised in chat."""
    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:8]}")
    session_id: str
    version: int = 1
    goal: str
    summary: str
    implementation_method: str = "direct_code_edit"  # "direct_code_edit", "game_creation", "gds_patch", "composer", "pipeline"
    steps: List[PlanStep] = Field(default_factory=list)
    status: PlanArtifactStatus = "awaiting_approval"
    proceed_confirmed: bool = False
    revisions: List[PlanRevision] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def record_revision(self, user_prompt: str, summary_of_changes: str) -> None:
        """Records a user revision and increments the plan version."""
        self.version += 1
        self.revisions.append(
            PlanRevision(
                version=self.version,
                user_prompt=user_prompt,
                summary_of_changes=summary_of_changes,
                timestamp=time.time(),
            )
        )
        self.status = "awaiting_approval"
        self.proceed_confirmed = False
        self.updated_at = time.time()

    def confirm_proceed(self) -> None:
        """Marks the plan approved and ready for execution."""
        self.proceed_confirmed = True
        self.status = "approved"
        self.updated_at = time.time()

    def update_step_status(
        self,
        step_id: str,
        status: PlanStepStatus,
        output_summary: Optional[str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Updates the status of a specific plan step."""
        for step in self.steps:
            if step.step_id == step_id:
                step.status = status
                if output_summary is not None:
                    step.output_summary = output_summary
                if error is not None:
                    step.error = error
                self.updated_at = time.time()
                return True
        return False

    def to_markdown(self) -> str:
        """Renders the plan into clean GitHub-flavored markdown for chat presentation."""
        status_badges = {
            "draft": "Draft",
            "awaiting_approval": "Awaiting Approval",
            "approved": "Approved — Ready to Execute",
            "executing": "Executing...",
            "completed": "Completed",
            "rejected": "Rejected",
        }
        badge = status_badges.get(self.status, self.status)
        ver_text = f" (v{self.version})" if self.version > 1 else ""

        md_lines = [
            f"### Technical Plan: {self.goal}{ver_text}",
            f"**Status:** `{badge}` | **Method:** `{self.implementation_method}`\n",
            f"{self.summary}\n",
            "#### Proposed Implementation Steps",
        ]

        step_icons = {
            "pending": "⏳",
            "in_progress": "🔄",
            "completed": "✅",
            "failed": "❌",
            "skipped": "⏭️",
        }

        for idx, step in enumerate(self.steps, start=1):
            icon = step_icons.get(step.status, "•")
            files_part = f" (`{', '.join(step.target_files)}`)" if step.target_files else ""
            tools_part = f" _[tools: {', '.join(step.tools)}]_" if step.tools else ""
            md_lines.append(f"{idx}. {icon} **{step.title}**{files_part}{tools_part}")
            if step.description:
                md_lines.append(f"   - {step.description}")
            if step.verification:
                md_lines.append(f"   - *Verification:* {step.verification}")
            if step.output_summary:
                md_lines.append(f"   - *Result:* {step.output_summary}")
            if step.error:
                md_lines.append(f"   - *Error:* `{step.error}`")

        if self.revisions:
            md_lines.append("\n#### Revision History")
            for rev in self.revisions:
                md_lines.append(f"- **v{rev.version}:** {rev.summary_of_changes} _(from: \"{rev.user_prompt[:60]}...\")_")

        if self.status == "awaiting_approval":
            md_lines.append("\n> **Awaiting Confirmation:** Click **Proceed** to execute this plan, or send follow-up instructions to refine it.")

        return "\n".join(md_lines)
