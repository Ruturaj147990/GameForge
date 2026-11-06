"""Comprehensive test suite verifying Stage 1 backend re-engineering, capability truthfulness,
disclaimer remediation, multi-file code block extraction, tool result contracts, and boundary security."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.gameforge_ide.backend.agent.context_manager import ContextManager
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.models.capability import RuntimeCapabilityRegistry, RuntimeCapabilityStatus
from src.gameforge_ide.backend.models.modes import AutonomyProfile, TaskMode
from src.gameforge_ide.backend.providers.router import ModelRouter
from src.gameforge_ide.backend.security.boundary import BoundaryManager
from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.backend.tools.edit_tools import EditTools


def _make_runtime(workspace: Path) -> AgentRuntime:
    db_path = workspace / ".gameforge" / "sessions.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sm = SessionManager(db_path)
    router = ModelRouter()
    return AgentRuntime(workspace, sm, router)


# ==============================================================================
# 1. Capability Truthfulness & Disclaimer Remediation Tests (Section 3.2)
# ==============================================================================

def test_detect_false_capability_disclaimer_patterns():
    """Verify _detect_false_capability_disclaimer catches multiple common refusal patterns."""
    disclaimers = [
        "I am an AI text assistant, not an automation engine, so I cannot execute code.",
        "As an AI language model, I cannot access your filesystem or modify files directly.",
        "I don't have the ability to run commands or launch Unreal Engine.",
        "Unfortunately, I cannot compile code or run build tools.",
        "You'll need to manually copy this code snippet into Source/Player.cpp and compile it yourself.",
        "Please create the file Source/Hero.h manually and paste the following implementation.",
        "As I cannot directly create files in your workspace, here is the code you should save.",
    ]
    for d in disclaimers:
        assert AgentRuntime._detect_false_capability_disclaimer(d) is True, f"Failed to detect: {d}"

    # Legitimate non-disclaimer responses must return False
    valid_responses = [
        "I will now inspect the project structure and edit Source/Weapon.cpp.",
        "Here is the diff that was applied to add the stamina system.",
        "The compilation succeeded with 0 warnings and 0 errors.",
        "Unreal Engine replication uses server-authoritative RPCs and replicated properties (UPROPERTY(Replicated)).",
    ]
    for v in valid_responses:
        assert AgentRuntime._detect_false_capability_disclaimer(v) is False, f"False positive on: {v}"


def test_rectify_false_capability_disclaimer():
    """Verify _rectify_false_capability_disclaimer removes refusal language and asserts real capabilities."""
    refusal = (
        "I am an AI text assistant, not an automation engine, so I cannot edit files.\n"
        "You will need to manually copy this into Weapon.cpp.\n"
        "Here is the implementation:\n"
        "class AWeapon : public AActor {};"
    )
    rectified = AgentRuntime._rectify_false_capability_disclaimer(refusal)
    assert "not an automation engine" not in rectified
    assert "manually copy" not in rectified
    assert "As GameForge's autonomous assistant, I have direct workspace access" in rectified
    assert "class AWeapon" in rectified


def test_runtime_capability_registry_format():
    """Verify RuntimeCapabilityRegistry formats an informative, authoritative prompt block."""
    reg = RuntimeCapabilityRegistry()
    prompt_block = reg.format_prompt_block()
    assert "=== GAMEFORGE RUNTIME CAPABILITIES ===" in prompt_block
    assert "Filesystem & Code Editing:" in prompt_block
    assert "Command Execution Gateway:" in prompt_block
    assert "Unreal Engine 5.7 Integration:" in prompt_block
    assert "Autonomous 11-Stage Forge Pipeline:" in prompt_block
    assert "Automated Diagnosis & Repair Engine:" in prompt_block
    assert "TRUTHFULNESS & CAPABILITY MANDATE:" in prompt_block


def test_conversational_action_verbs_classification():
    """Verify that requests with explicit action verbs (edit, compile, test, write) are not treated as conversational."""
    actionable_prompts = [
        "Can you edit player.cpp to increase speed?",
        "Can you compile the project?",
        "Can you test the game?",
        "Can you check the compilation errors?",
        "Can you write a health component for the hero?",
        "Add a double jump mechanic to character.cpp",
        "Inspect the project directory",
    ]
    for p in actionable_prompts:
        assert AgentRuntime._is_conversational(p) is False, f"Should be actionable: {p}"

    pure_conversational = [
        "What are your capabilities?",
        "What does the assistant do?",
        "Explain how Unreal Engine replication works",
        "Hello there!",
        "How do actors replicate in UE5?",
    ]
    for p in pure_conversational:
        assert AgentRuntime._is_conversational(p) is True, f"Should be conversational: {p}"


# ==============================================================================
# 2. Sequential Multi-File Code Block Extraction Tests (Section 3.3)
# ==============================================================================

def test_extract_code_block_as_write_file_target_discovery(temp_workspace: Path):
    """Verify _extract_code_block_as_write_file resolves paths from headers, prompt, and class names."""
    runtime = _make_runtime(temp_workspace)

    # 1. Path in header comment // Path: Source/MyActor.cpp
    resp1 = """```cpp
// Path: Source/MyActor.cpp
#include "MyActor.h"
AMyActor::AMyActor() {}
```"""
    tc1 = runtime._extract_tool_call(resp1, user_prompt="Add actor")
    assert tc1 is not None
    assert (tc1.get("name") or tc1.get("tool")) == "write_file"
    assert tc1.get("arguments", {}).get("subpath") == "Source/MyActor.cpp"

    # 2. Path in user prompt
    resp2 = """```cpp
#include "Hero.h"
AHero::AHero() {}
```"""
    tc2 = runtime._extract_tool_call(resp2, user_prompt="Please write Source/Hero.cpp")
    assert tc2 is not None
    assert (tc2.get("name") or tc2.get("tool")) == "write_file"
    assert tc2.get("arguments", {}).get("subpath") == "Source/Hero.cpp"

    # 3. Class name heuristic in Unreal Engine project
    resp3 = """```cpp
#include "GameFramework/Actor.h"
class AInventoryManager : public AActor {};
```"""
    tc3 = runtime._extract_tool_call(resp3, user_prompt="Implement the inventory manager class")
    assert tc3 is not None
    assert (tc3.get("name") or tc3.get("tool")) == "write_file"
    assert "InventoryManager" in tc3.get("arguments", {}).get("subpath")


def test_extract_code_block_multi_file_sequential(temp_workspace: Path):
    """Verify sequential multi-file extraction skips already_modified files."""
    runtime = _make_runtime(temp_workspace)

    # Model emits both header and cpp in one response or sequential prompts
    resp_multi = """Here is the header:
```cpp
// Source/Player.h
#pragma once
class APlayer {};
```

And here is the implementation:
```cpp
// Source/Player.cpp
#include "Player.h"
```"""

    # First turn: neither is modified -> extracts Player.h
    tc_first = runtime._extract_tool_call(resp_multi, user_prompt="Create player header and cpp", already_modified=set())
    assert tc_first is not None
    assert tc_first["arguments"]["subpath"] == "Source/Player.h"

    # Second turn: Player.h is in already_modified -> extracts Player.cpp!
    tc_second = runtime._extract_tool_call(resp_multi, user_prompt="Create player header and cpp", already_modified={"Source/Player.h"})
    assert tc_second is not None
    assert tc_second["arguments"]["subpath"] == "Source/Player.cpp"


# ==============================================================================
# 3. EditTools Diff Contract & Population Tests
# ==============================================================================

def test_write_file_populates_both_diff_and_diff_patch(temp_workspace: Path):
    """Verify write_file populates both diff and diff_patch keys on SUCCESS."""
    boundary = BoundaryManager(temp_workspace)
    tools = EditTools(boundary)

    res = tools.write_file(
        subpath="Source/TestFile.cpp",
        content="// initial content\nint x = 42;\n",
    )
    assert res.get("status") == "SUCCESS"
    assert "diff" in res
    assert "diff_patch" in res
    assert res["diff"] == res["diff_patch"]
    assert "TestFile.cpp" in res["diff"]


# ==============================================================================
# 4. Security Boundary Clean Return
# ==============================================================================

def test_boundary_manager_safe_path_validation(temp_workspace: Path):
    """Verify BoundaryManager validates workspace containment without redundant execution."""
    boundary = BoundaryManager(temp_workspace)
    safe_file = temp_workspace / "Config" / "DefaultEngine.ini"
    safe_file.parent.mkdir(parents=True, exist_ok=True)
    safe_file.write_text("[Core]", encoding="utf-8")

    resolved = boundary.validate_path("Config/DefaultEngine.ini", allow_write=False)
    assert resolved == safe_file.resolve()
    assert boundary.is_safe("Config/DefaultEngine.ini", allow_write=False) is True


# ==============================================================================
# 5. Suspended Approval Tool Name Resolution
# ==============================================================================

def test_resume_task_after_approval_uses_resolved_tool(temp_workspace: Path):
    """Verify resume_task_after_approval defaults to resolved_tool instead of printing 'Tool None'."""
    async def _run():
        runtime = _make_runtime(temp_workspace)
        session = runtime.session_manager.create_session("Test Approval", "none", "ollama")
        sid = session.session_id

        # Seed an active task
        task_state = runtime._active_tasks[sid] = runtime.get_task_state(sid) or MagicMock()
        task_state.task_id = "task_test_123"
        task_state.phase = "author"
        task_state.ledger = []
        task_state.acceptance = []
        task_state.evaluate_acceptance.return_value = (True, [])

        tool_result = {"status": "SUCCESS", "exit_code": 0, "stdout": "Compilation succeeded"}

        events = []
        async for ev in runtime.resume_task_after_approval(
            session_id=sid,
            approval_id="appr_456",
            tool_result=tool_result,
            approved=True,
            tool_name=None,  # Not explicitly passed
        ):
            events.append(ev)

        done_ev = next(e for e in events if e.event_type == "done")
        assert "Tool `None`" not in done_ev.content
        assert "run_command" in done_ev.content

    asyncio.run(_run())
